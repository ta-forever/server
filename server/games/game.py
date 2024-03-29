import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, Iterable

import sqlalchemy
from sqlalchemy.exc import DBAPIError
from sqlalchemy import and_, bindparam, text
from sqlalchemy.sql.functions import now as sql_now

from server.config import FFA_TEAM, config
from server.db.models import (
    game_player_stats,
    game_stats,
    matchmaker_queue_game
)
from server.games.game_results import (
    ArmyOutcome,
    ArmyReportedOutcome,
    GameOutcome,
    GameResolutionError,
    GameResultReport,
    GameResultReports,
    resolve_game
)
from server.rating import InclusiveRange, RatingType

from ..abc.base_game import GameConnectionState, InitMode
from ..players import Player, PlayerState
from .typedefs import (
    FA,
    BasicGameInfo,
    EndedGameInfo,
    FeaturedModType,
    GameState,
    GameType,
    ValidityState,
    Victory,
    VisibilityState
)


class GameError(Exception):
    pass


class Game():
    """
    Object that lasts for the lifetime of a game on FAF.
    """

    # these are overriden by derived classes
    # Game.__init__() sees the derived classes' override
    init_mode = None
    game_type = None

    def __init__(
        self,
        id_: int,
        database: "FAFDatabase",
        game_service: "GameService",
        game_stats_service: "GameStatsService",
        host: Optional[Player] = None,
        name: str = "None",
        map_: str = "SHERWOOD",
        game_mode: str = FeaturedModType.DEFAULT,
        mod_version: str = None,
        matchmaker_queue_id: Optional[int] = None,
        rating_type: Optional[str] = None,
        displayed_rating_range: Optional[InclusiveRange] = None,
        enforce_rating_range: bool = False,
        max_players: int = 10,
        replay_delay_seconds: int = 300,     # or negative to disable
        map_pool_map_ids: Iterable[int] = None,
        galactic_war_planet_name: str = None
    ):
        self._logger.info(f"[Game.__init__] id={id}, game_mode={game_mode}, rating_type={rating_type}")
        self._db = database
        self._results = GameResultReports(id_)
        self._army_stats_list = []
        self._players_with_unsent_army_stats = []
        self._game_stats_service = game_stats_service
        self.game_service = game_service
        self._player_options: Dict[int, Dict[str, Any]] = defaultdict(dict)
        self.launched_at = None
        self.ended = False
        self._logger = logging.getLogger(
            "{}.{}".format(self.__class__.__qualname__, id_)
        )
        self.id = id_
        self.visibility = VisibilityState.PUBLIC
        self.max_players = max_players
        self.host = host
        self.name = name
        self.map_id = None
        self.map_file_path = f"/{map_}/"
        self.map_ranked = False
        self.password = None
        self._players = []
        self.AIs = {}
        self.desyncs = 0
        self.validity = ValidityState.VALID
        self.game_mode = game_mode
        self.mod_version = mod_version
        self.rating_type = rating_type or RatingType.GLOBAL     # NB potentially overriden to GLOBAL on game going live
        self.rating_type_preferred = self.rating_type
        self.displayed_rating_range = displayed_rating_range or InclusiveRange()
        self.enforce_rating_range = enforce_rating_range
        self.matchmaker_queue_id = matchmaker_queue_id
        self.state = GameState.INITIALIZING
        self.replay_delay_seconds = replay_delay_seconds
        self.galactic_war_planet_name = galactic_war_planet_name
        self._connections = {}
        self.enforce_rating = False
        self.gameOptions = {
            "FogOfWar": "explored",
            "GameSpeed": "normal",
            "Victory": Victory.DEMORALIZATION,
            "CheatsEnabled": "false",
            "PrebuiltUnits": "Off",
            "NoRushOption": "Off",
            "TeamLock": "locked",
            "AIReplacement": "Off",
            "RestrictedCategories": 0
        }
        self.player_pings = {}
        self.mods = {}

        self.map_pool_map_ids = None
        if map_pool_map_ids is not None:
            self.map_pool_map_ids = set(id_ for id_ in map_pool_map_ids)

        # @todo maintenance hazard. consider storing GameState itself in the future instead of boolean?
        self._is_hosted_staging = asyncio.Future()
        self._is_hosted_battleroom = asyncio.Future()
        self._launch_fut = asyncio.Future()

        self._logger.debug("%s created", self)

    async def timeout_hosted_staging(self, timeout: int = 60):
        await asyncio.sleep(timeout)
        if self.state in [GameState.INITIALIZING]:
            self._is_hosted_staging.set_exception(asyncio.TimeoutError("Timeout waiting for hosted/staging"))
            self._logger.debug("Game setup timed out waiting for hosted/staging ... Cancelling game")
            await self.on_game_end()

    async def timeout_hosted_battleroom(self, timeout: int = 60):
        await asyncio.sleep(timeout)
        if self.state in [GameState.INITIALIZING, GameState.STAGING]:
            self._is_hosted_battleroom.set_exception(asyncio.TimeoutError("Timeout waiting for hosted/battleroom"))
            self._logger.debug("Game setup timed out waiting for hosted/battleroom ... Cancelling game")
            await self.on_game_end()

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value: str):
        """
        Verifies that names only contain ascii characters.
        """
        if not value.isascii():
            raise ValueError("Name must be ascii!")

        self.set_name_unchecked(value)

    def set_name_unchecked(self, value: str):
        """
        Sets the game name without doing any validity checks.

        Truncates the game name to avoid crashing mysql INSERT statements.
        """
        max_len = game_stats.c.gameName.type.length
        self._name = value[:max_len]

    @property
    def armies(self):
        return frozenset(
            self.get_player_option(player.id, "Army")
            for player in self.players
        )

    @property
    def players(self):
        """
        Players in the game

        Depending on the GameState, it is either:
          - (STAGING/BATTLEROOM/LAUNCHING) The currently connected players
          - (LIVE) Players who participated in the game
          - Empty list
        :return: frozenset
        """
        if self.state in (GameState.STAGING, GameState.BATTLEROOM, GameState.LAUNCHING):
            return frozenset(
                player for player in self._connections.keys()
                if player.id in self._player_options
            )
        else:
            return frozenset(
                player for player, army in (
                    (player, self.get_player_option(player.id, "Army"))
                    for player in self._players
                )
                if army is not None and army >= 0
            )

    def get_player_alias(self, player: Player) -> str:
        raise NotImplementedError()

    @property
    def connections(self):
        return self._connections.values()

    @property
    def teams(self):
        """
        A set of all teams of this game's players.
        """
        teams = [ self.get_player_option(player.id, "Team")
                  for player in self.players ]
        return frozenset(team for team in teams if team is not None and team>=0)

    def is_pooled_map(self, map_id):
        """
        :return: True if given map_id is a member of the game's map pool, or if game's map pool is None
        """
        return map_id is not None and (self.map_pool_map_ids is None or map_id in self.map_pool_map_ids)

    @property
    def is_mutually_agreed_draw(self) -> bool:
        return self._results.is_mutually_agreed_draw(self.armies)

    @property
    def is_ffa(self) -> bool:
        if len(self.players) < 3:
            return False

        return FFA_TEAM in self.teams

    @property
    def is_multi_team(self) -> bool:
        return len(self.teams) > 2

    @property
    def has_ai(self) -> bool:
        return len(self.AIs) > 0

    @property
    def is_even(self) -> bool:
        """
        Returns True iff all teams have the same player count, taking into account that players on the FFA team are in individual teams.
        Special cases:
         - Returns True if there are zero teams.
         - Returns False if there is a single team.
        """
        teams = self.get_team_sets()
        if len(teams) == 0:
            return True
        if len(teams) == 1:
            return False

        team_sizes = set(len(team) for team in teams)
        return len(team_sizes) == 1

    def get_team_sets(self) -> List[Set[Player]]:
        """
        Returns a list of teams represented as sets of players.
        Note that FFA players will be separated into individual teams.
        """
        if None in self.teams:
            raise GameError(
                "Missing team for at least one player. (player, team): {}"
                .format([(player, self.get_player_option(player.id, "Team"))
                        for player in self.players])
            )

        teams = defaultdict(set)
        ffa_players = []
        for player in self.players:
            team_id = self.get_player_option(player.id, "Team")
            if team_id == FFA_TEAM:
                ffa_players.append({player})
            elif team_id >= 0:
                teams[team_id].add(player)

        return list(teams.values()) + ffa_players

    async def wait_hosted(self, timeout: float):
        if self.init_mode == InitMode.AUTO_LOBBY:
            return await asyncio.wait_for(asyncio.shield(
                self._is_hosted_battleroom), timeout=timeout)
        else:
            return await asyncio.wait_for(asyncio.shield(
                self._is_hosted_staging), timeout=timeout)

    def set_hosted_staging(self, value: bool = True):
        if not self._is_hosted_staging.done():
            self._is_hosted_staging.set_result(value)

    def set_hosted_battleroom(self):
        if not self._is_hosted_battleroom.done():
            self._is_hosted_battleroom.set_result(None)

    async def wait_launched(self, timeout: float):
        return await asyncio.wait_for(
            asyncio.shield(self._launch_fut),
            timeout=timeout
        )

    async def add_result(
        self, reporter: int, army: int, result_type: str, score: int
    ):
        """
        As computed by the game.
        :param reporter: player ID
        :param army: the army number being reported for
        :param result_type: a string representing the result
        :param score: an arbitrary number assigned with the result
        :return:
        """
        if army not in self.armies:
            self._logger.debug("Game.add_result(reporter=%s,army=%s,result_type=%s,score=%s",
                repr(reporter), repr(army), repr(result_type), repr(score))
            self._logger.debug("  Ignoring results for unknown army. Known armies are:%s", repr(self.armies))
            return

        try:
            outcome = ArmyReportedOutcome(result_type.upper())
        except ValueError:
            self._logger.debug(
                "Ignoring result reported by %s for army %s: %s %s",
                reporter, army, result_type, score
            )
            return

        result = GameResultReport(reporter, army, outcome, score)
        self._results.add(result)
        self._logger.info(
            "%s reported result for army %s: %s %s", reporter, army,
            result_type, score
        )

        self._process_pending_army_stats()

    def _process_pending_army_stats(self):
        for player in self._players_with_unsent_army_stats:
            army = self.get_player_option(player.id, "Army")
            if army not in self._results:
                continue

            for result in self._results[army]:
                if result.outcome is not GameOutcome.UNKNOWN:
                    self._process_army_stats_for_player(player)
                    break

    def _process_army_stats_for_player(self, player):
        try:
            if (
                len(self._army_stats_list) == 0
                or self.gameOptions["CheatsEnabled"] != "false"
            ):
                return

            self._players_with_unsent_army_stats.remove(player)
            # Stat processing contacts the API and can take quite a while so
            # we don't want to await it
            asyncio.create_task(
                self._game_stats_service.process_game_stats(
                    player, self, self._army_stats_list
                )
            )
        except Exception:
            # Never let an error in processing army stats cascade
            self._logger.exception(
                "Army stats could not be processed from player %s in game %s",
                player, self
            )

    def add_game_connection(self, game_connection):
        """
        Add a game connection to this game
        :param game_connection:
        :return:
        """
        if game_connection.state != GameConnectionState.CONNECTED_TO_HOST:
            raise GameError(
                f"Invalid GameConnectionState: {game_connection.state}"
            )
        if self.state is GameState.INITIALIZING:
            raise GameError(f"Invalid GameState: {self.state}")

        if len(self._connections) >= self.max_players:
            raise GameError("Game is full")

        self._logger.info("Added game connection %s", game_connection)
        self._connections[game_connection.player] = game_connection

    async def remove_game_connection(self, game_connection):
        """
        Remove a game connection from this game

        Will trigger on_game_end if there are no more active connections to the game
        :param peer:
        :param
        :return: None
        """
        if game_connection not in self._connections.values():
            return

        player = game_connection.player
        del self._connections[player]
        del player.game

        if self.state in (GameState.STAGING, GameState.BATTLEROOM) and player.id in self._player_options:
            del self._player_options[player.id]

        await self.check_sim_end()

        self._logger.info("Removed game connection %s", game_connection)

        host_left_lobby = (
            player == self.host and self.state in (GameState.STAGING, GameState.BATTLEROOM)
        )

        if self.state is not GameState.ENDED and (
            self.ended or
            len(self._connections) == 0 or
            host_left_lobby
        ):
            await self.on_game_end()
        else:
            self._process_pending_army_stats()

    async def check_sim_end(self):
        if self.ended:
            return
        if self.state not in (GameState.LAUNCHING, GameState.LIVE):
            return
        if [conn for conn in self.connections if not conn.finished_sim]:
            return
        self.ended = True
        async with self._db.acquire() as conn:
            await conn.execute(
                game_stats.update().where(
                    game_stats.c.id == self.id
                ).values(
                    endTime=sql_now()
                )
            )

    async def on_game_end(self):
        try:
            if self.state is GameState.INITIALIZING:
                self._logger.info("Game cancelled pre initialization")
            elif self.state is GameState.STAGING:
                self._logger.info("Game cancelled while staging")
            elif self.state is GameState.BATTLEROOM:
                self._logger.info("Game cancelled in battleroom")
            elif self.state is GameState.LAUNCHING:
                self._logger.info("Game cancelled while launching")
            elif self.state is GameState.LIVE:
                self._logger.info("Game finished normally")

                if self.desyncs > 20:
                    await self.mark_invalid(ValidityState.TOO_MANY_DESYNCS)
                    return

                if self.is_mutually_agreed_draw:
                    self._logger.info("Game is a mutual draw")
                    await self.mark_invalid(ValidityState.MUTUAL_DRAW)
                    return

                await self.process_game_results()

                self._process_pending_army_stats()
        except Exception:    # pragma: no cover
            self._logger.exception("Error during game end")
        finally:
            self.state = GameState.ENDED

            self.game_service.mark_dirty(self)

    async def _run_pre_rate_validity_checks(self):
        pass

    async def process_game_results(self):
        if not self._results:
            await self.mark_invalid(ValidityState.UNKNOWN_RESULT)
            return

        await self.persist_results()

        game_results = await self.resolve_game_results()
        await self.game_service.publish_game_results(game_results)

    async def resolve_game_results(self) -> EndedGameInfo:
        if self.state not in (GameState.LIVE, GameState.ENDED):
            raise GameError("Cannot rate game that has not gone live.")

        await self._run_pre_rate_validity_checks()

        basic_info = self.get_basic_info()
        team_outcomes = [GameOutcome.UNKNOWN for _ in basic_info.teams]

        if self.validity is ValidityState.VALID:
            try:
                team_player_partial_outcomes = [
                    {self.get_player_outcome(player) for player in team}
                    for team in basic_info.teams
                ]
                # TODO: Remove override once game result messages are reliable
                team_outcomes = (
                    self._outcome_override_hook()
                    or resolve_game(team_player_partial_outcomes)
                )
            except GameResolutionError:
                await self.mark_invalid(ValidityState.UNKNOWN_RESULT)

        try:
            commander_kills = {
                army_stats["name"]: army_stats["units"]["cdr"]["kills"]
                for army_stats in self._army_stats_list
            }
        except KeyError:
            commander_kills = {}

        return EndedGameInfo.from_basic(
            basic_info, self.validity, team_outcomes, commander_kills
        )

    def _outcome_override_hook(self) -> Optional[List[GameOutcome]]:
        return None

    async def load_results(self):
        """
        Load results from the database
        :return:
        """
        self._results = await GameResultReports.from_db(self._db, self.id)

    async def persist_results(self):
        """
        Persist game results into the database

        Requires the game to have been launched and the appropriate rows to exist in the database.
        :return:
        """

        self._logger.debug("Saving scores from game %s", self.id)
        scores = {}
        for player in self.players:
            army = self.get_player_option(player.id, "Army")
            outcome = self.get_player_outcome(player)
            score = self.get_army_score(army)
            scores[player] = (score, outcome)
            self._logger.info(
                "Result for army %s, player: %s: score %s, outcome %s",
                army, player, score, outcome
            )

        async with self._db.acquire() as conn:
            rows = []
            for player, (score, outcome) in scores.items():
                self._logger.info(
                    "Score for player %s: score %s, outcome %s",
                    player, score, outcome,
                )
                rows.append(
                    {
                        "score": score,
                        "result": outcome.name.upper(),
                        "game_id": self.id,
                        "player_id": player.id,
                    }
                )

            update_statement = game_player_stats.update().where(
                and_(
                    game_player_stats.c.gameId == bindparam("game_id"),
                    game_player_stats.c.playerId == bindparam("player_id"),
                )
            ).values(
                score=bindparam("score"),
                scoreTime=sql_now(),
                result=bindparam("result"),
            )
            await conn.deadlock_retry_execute(update_statement, rows)

    def get_basic_info(self) -> BasicGameInfo:
        return BasicGameInfo(
            self.id,
            self.rating_type,
            self.map_id,
            self.map_name,
            self.game_mode,
            self.galactic_war_planet_name,
            list(self.mods.keys()),
            self.get_team_sets(),
        )

    def set_player_option(self, player_id: int, key: str, value: Any):
        """
        Set game-associative options for given player, by id

        :param player_id: The given player's id
        :param key: option key string
        :param value: option value
        """
        self._player_options[player_id][key] = value
        if key == 'Faction':
            for player in self.players:
                if player.id == player_id:
                    player.faction = int(value)
                    break

    def get_player_option(self, player_id: int, key: str) -> Optional[Any]:
        """
        Retrieve game-associative options for given player, by their uid
        :param player_id: The id of the player
        :param key: The name of the option
        """
        return self._player_options[player_id].get(key)

    def set_ai_option(self, name, key, value):
        """
        This is a noop for now
        :param name: Name of the AI
        :param key: option key string
        :param value: option value
        :return:
        """
        if name not in self.AIs:
            self.AIs[name] = {}
        self.AIs[name][key] = value

    def clear_slot(self, slot_index):
        """
        A somewhat awkward message while we're still half-slot-associated with a bunch of data.

        Just makes sure that any players associated with this
        slot aren't assigned an army or team, and deletes any AI's.
        :param slot_index:
        :return:
        """
        for player in self.players:
            if self.get_player_option(player.id, "StartSpot") == slot_index:
                self.set_player_option(player.id, "Team", -1)
                self.set_player_option(player.id, "Army", -1)
                self.set_player_option(player.id, "StartSpot", -1)

        to_remove = []
        for ai in self.AIs:
            if self.AIs[ai]["StartSpot"] == slot_index:
                to_remove.append(ai)
        for item in to_remove:
            del self.AIs[item]

    async def validate_game_settings(self):
        """
        Mark the game invalid if it has non-compliant options
        """

        # Only allow ranked mods
        for mod_id in self.mods.keys():
            if mod_id not in self.game_service.ranked_mods:
                await self.mark_invalid(ValidityState.BAD_MOD)
                return

        if self.has_ai:
            await self.mark_invalid(ValidityState.HAS_AI_PLAYERS)
            return
        if self.is_multi_team:
            await self.mark_invalid(ValidityState.MULTI_TEAM)
            return
        if self.is_ffa:
            await self.mark_invalid(ValidityState.FFA_NOT_RANKED)
            return
        valid_options = {
            "AIReplacement": (FA.FALSE, ValidityState.HAS_AI_PLAYERS),
            "FogOfWar": ("explored", ValidityState.NO_FOG_OF_WAR),
            "CheatsEnabled": (FA.FALSE, ValidityState.CHEATS_ENABLED),
            "PrebuiltUnits": (FA.FALSE, ValidityState.PREBUILT_ENABLED),
            "NoRushOption": (FA.FALSE, ValidityState.NORUSH_ENABLED),
            "RestrictedCategories": (0, ValidityState.BAD_UNIT_RESTRICTIONS),
            "TeamLock": ("locked", ValidityState.UNLOCKED_TEAMS)
        }
        if await self._validate_game_options(valid_options) is False:
            return

        await self.validate_game_mode_settings()

    async def validate_game_mode_settings(self):
        """
        A subset of checks that need to be overridden in coop games.
        """
        if None in self.teams or not self.is_even:
            await self.mark_invalid(ValidityState.UNEVEN_TEAMS_NOT_RANKED)
            return

        if len(self.players) < 2:
            await self.mark_invalid(ValidityState.SINGLE_PLAYER)
            return

        valid_options = {
            "Victory": (Victory.DEMORALIZATION, ValidityState.WRONG_VICTORY_CONDITION)
        }
        await self._validate_game_options(valid_options)

    async def _validate_game_options(
        self, valid_options: Dict[str, Tuple[Any, ValidityState]]
    ) -> bool:
        for key, value in self.gameOptions.items():
            if key in valid_options:
                (valid_value, validity_state) = valid_options[key]
                if self.gameOptions[key] != valid_value:
                    await self.mark_invalid(validity_state)
                    return False
        return True

    async def on_launching(self, player_service):
        self._logger.debug(f"[on_launching] gameid={self.id}, state={self.state}")
        if self.state is GameState.BATTLEROOM:
            self.state = GameState.LAUNCHING
            self.launched_at = time.time()
            self._logger.info("Game LAUNCHING")
            for player in self.players:
                player_service.set_player_state(player, PlayerState.PLAYING)

    async def on_live(self):
        """
        Mark the game as live.

        Freezes the set of active players so they are remembered if they drop.
        :return: None
        """
        self._logger.debug(f"[on_live] gameid={self.id}, state={self.state}")
        if self.state is GameState.LAUNCHING:
            self._players = self.players
            self._players_with_unsent_army_stats = list(self._players)

            self.assign_rating_type(strict_team_size=True)

            self.state = GameState.LIVE
            self._logger.info("Game LIVE")

            await self.persist_game_stats()
            await self.persist_game_player_stats()
            await self.persist_mod_stats()
            await self.validate_game_settings()

            self._launch_fut.set_result(None)
            self._logger.info("Game launched")

    def find_suitable_rating_queue(self, strict_team_size: bool, strict_map_pool: bool):
        if strict_team_size:
            teams = self.get_team_sets()
            if len(teams) != 2:
                self._logger.info(f"[find_suitable_rating_queue] Game {self.id}: no suitable queue because len(teams)={len(teams)}!=2")
                return None

            team_size = [len(players) for players in teams]
            if team_size[0] != team_size[1]:
                self._logger.info(f"[find_suitable_rating_queue] Game {self.id}: no suitable queue because team_sizes {team_size} are not equal")
                return None
            team_size = team_size[0]

        else:
            player_count = sum([len(players) for players in self.get_team_sets()])
            team_size = (1+player_count)//2

        # largest queue by team size such that queue_size <= team_size
        best_queue = None
        available_ranked_map_ids = [m.id for m in self.game_service.get_available_ranked_maps()]
        for queue in self.game_service.get_available_matchmaker_queues().values():
            if queue.featured_mod == self.game_mode and queue.team_size <= team_size:
                if strict_map_pool:
                    pool = queue.get_map_pool_for_rating(1500)
                    if pool and self.map_id not in pool.get_map_ids():
                        self._logger.info(f"[find_suitable_rating_queue] Game {self.id}: rejecting queue {queue.name} because game's map {self.map_id} is not in the queue's map pool")
                        continue
                elif self.map_id not in available_ranked_map_ids:
                    self._logger.info(f"[find_suitable_rating_queue] Game {self.id}: rejecting queue {queue.name} because game's map {self.map_id} is not a ranked map")
                    continue

                if best_queue is None or best_queue.team_size < queue.team_size:
                    best_queue = queue

        return best_queue

    def find_suitable_rating_type(self, strict_team_size: bool, strict_map_pool: bool):
        queue = self.find_suitable_rating_queue(strict_team_size, strict_map_pool)
        return queue.rating_type if queue is not None else RatingType.GLOBAL

    def assign_rating_type(self, strict_team_size: bool):

        if self.state not in (GameState.STAGING, GameState.BATTLEROOM, GameState.LAUNCHING):
            self._logger.info(f"[assign_rating_type] Game {self.id}: leaving rating_type={self.rating_type} because state {self.state}")
            return

        if self.rating_type_preferred == RatingType.GLOBAL:
            self._logger.info(f"[assign_rating_type] Game {self.id}: ensuring rating_type global because preferred")
            self.rating_type = RatingType.GLOBAL
            self.matchmaker_queue_id = None
            self.map_pool_map_ids = None
            return

        if self.game_type == GameType.MATCHMAKER:
            assert(self.matchmaker_queue_id is not None)
            self._logger.info(f"[assign_rating_type] Game {self.id}: respecting rating_type_preferred {self.rating_type_preferred} because GameType.MATCHMAKER")
            self.rating_type = self.rating_type_preferred
            return

        default_ranked_maps = self.game_service.get_available_ranked_maps()
        default_ranked_map_ids = None if default_ranked_maps is None else set([m.id for m in default_ranked_maps])
        self.map_pool_map_ids = default_ranked_map_ids

        queue = self.find_suitable_rating_queue(strict_team_size=strict_team_size, strict_map_pool=config.STRICT_MAP_POOL)
        if queue is None:
            self._logger.info(f"[assign_rating_type] Game {self.id}: no suitable queues found. setting to global")
            self.rating_type = RatingType.GLOBAL

        if queue is not None:
            self._logger.info(f"[assign_rating_type] Game {self.id}: selecting rating_type from queue {queue.name}")
            self.matchmaker_queue_id = queue.id
            self.rating_type = queue.rating_type
            if config.STRICT_MAP_POOL:
                pool = queue.get_map_pool_for_rating(1500)
                self.map_pool_map_ids = default_ranked_map_ids if pool is None else set(id_ for id_ in pool.get_map_ids())

    async def persist_mod_stats(self):
        if len(self.mods.keys()) > 0:
            async with self._db.acquire() as conn:
                uids = list(self.mods.keys())
                await conn.execute(text(
                    """ UPDATE mod_stats s JOIN mod_version v ON v.mod_id = s.mod_id
                        SET s.times_played = s.times_played + 1 WHERE v.uid in :ids"""),
                    ids=tuple(uids))

    def set_map(self, map_id, map_file_path, ranked):
        self.map_id = map_id
        self.map_file_path = map_file_path
        self.map_ranked = ranked

    async def fetch_map_file_path(self, default_hpi, map_name, crc):
        async with self._db.acquire() as conn:
            result = await conn.execute(sqlalchemy.sql.text(
                "SELECT id, filename, ranked FROM map_version " \
                "WHERE filename like :map_path order by version desc limit 1"),
                map_path="%/{}/{}".format(map_name, crc))
            row = result.fetchone()

        if row:
            self.set_map(row.id, row.filename, row.ranked)
        else:
            self._logger.debug(f"{map_name}/{crc} not found. defaulting to {default_hpi}/{map_name}/{crc} with id=None and unranked")
            self.set_map(None, f"{default_hpi}/{map_name}/{crc}", True)

    async def persist_game_stats(self):
        """
        Runs at game-start to populate the game_stats table (games that start are ones we actually
        care about recording stats for, after all).
        """
        assert self.host is not None

        if self.validity is ValidityState.VALID and not self.map_ranked:
            await self.mark_invalid(ValidityState.BAD_MAP)

        modId = self.game_service.featured_mods[self.game_mode].id

        # Write out the game_stats record.
        # In some cases, games can be invalidated while running: we check for those cases when
        # the game ends and update this record as appropriate.

        game_type = str(self.gameOptions.get("Victory").value)

        async with self._db.acquire() as conn:
            await conn.execute(
                game_stats.insert().values(
                    id=self.id,
                    gameType=game_type,
                    gameMod=modId,
                    host=self.host.id,
                    mapId=self.map_id,
                    gameName=self.name,
                    validity=self.validity.value,
                    replay_hidden=self.replay_delay_seconds < 0     # hide the replay is user requested no live replay
                )
            )

            if self.matchmaker_queue_id is not None:
                await conn.execute(
                    matchmaker_queue_game.insert().values(
                        matchmaker_queue_id=self.matchmaker_queue_id,
                        game_stats_id=self.id,
                    )
                )

    async def persist_game_player_stats(self):
        query_args = []
        for player in self.players:
            options = {
                key: self.get_player_option(player.id, key)
                for key in ["Team", "StartSpot", "Color", "Faction"]
            }

            is_observer = (
                options["Team"] is None
                or options["Team"] < 0
                or options["StartSpot"] is None
                or options["StartSpot"] < 0
            )
            if is_observer:
                continue

            # DEPRECATED: Rating changes are persisted by the rating service
            # in the `leaderboard_rating_journal` table.
            mean, deviation = player.ratings[self.rating_type]

            query_args.append(
                {
                    "gameId": self.id,
                    "playerId": player.id,
                    "faction": options["Faction"],
                    "color": options["Color"],
                    "team": options["Team"],
                    "place": options["StartSpot"],
                    "mean": mean,
                    "deviation": deviation,
                    "AI": 0,
                    "score": 0,
                }
            )
        if not query_args:
            self._logger.warning("No player options available!")
            return

        try:
            async with self._db.acquire() as conn:
                await conn.execute(game_player_stats.insert().values(query_args))
        except DBAPIError:
            self._logger.exception(
                "Failed to update game_player_stats. Query args %s:", query_args
            )
            raise

    async def mark_invalid(self, new_validity_state: ValidityState):
        self._logger.info(
            "Marked as invalid because: %s", repr(new_validity_state)
        )
        self.validity = new_validity_state

        # If we haven't started yet, the invalidity will be persisted to the database when we start.
        # Otherwise, we have to do a special update query to write this information out.
        if self.state not in (GameState.LAUNCHING, GameState.LIVE):
            return

        # Currently, we can only end up here if a game desynced or was a custom game that terminated
        # too quickly.
        async with self._db.acquire() as conn:
            await conn.execute(
                game_stats.update().where(
                    game_stats.c.id == self.id
                ).values(
                    validity=new_validity_state.value
                )
            )

    def get_army_score(self, army):
        return self._results.score(army)

    def get_player_outcome(self, player: Player) -> ArmyOutcome:
        army = self.get_player_option(player.id, "Army")
        if army is None:
            return ArmyOutcome.UNKNOWN

        return self._results.outcome(army)

    def report_army_stats(self, stats_json):
        self._army_stats_list = json.loads(stats_json)["stats"]
        self._process_pending_army_stats()

    def is_visible_to_player(self, player: Player) -> bool:
        if self.host is None:
            return False

        if self.state in (GameState.LAUNCHING, GameState.LIVE, GameState.ENDED):
            return True

        if player == self.host or player in self._connections:
            return True

        mean, dev = player.ratings[self.rating_type]
        displayed_rating = mean - 3 * dev
        if (
            self.enforce_rating_range
            and displayed_rating not in self.displayed_rating_range
        ):
            return False

        if self.visibility is VisibilityState.FRIENDS:
            return player.id in self.host.friends
        else:
            return player.id not in self.host.foes

    def update_player_pings(self, player_id: int, peer_pings_str: str):
        current_player_ids = set([p.id for p in self.players])
        self.player_pings[player_id] = [
            [pid2, ping]
            for (pid2, ping) in [[int(x) for x in pair.split(':')[0:2]] for pair in peer_pings_str.split(';')]
            if pid2 in current_player_ids
        ]
        self.player_pings = {
            pid: pings
            for (pid, pings) in self.player_pings.items()
            if pid in current_player_ids
        }

    def to_dict(self, pings_only=False):
        client_state = {
            GameState.INITIALIZING: "unknown",
            GameState.STAGING: "staging",
            GameState.BATTLEROOM: "battleroom",
            GameState.LAUNCHING: "launching",
            GameState.LIVE: "live",
            GameState.ENDED: "ended"
        }.get(self.state, "unknown")
        current_player_list = [p for p in self.players]

        result = {
            "command": "game_info",
            "uid": self.id,
            "state": client_state,
            "pings": self.player_pings
        }
        if not pings_only:
            self.assign_rating_type(strict_team_size=False)
            result.update({
                "visibility": self.visibility.value,
                "password_protected": self.password is not None,
                "title": self.name,
                "replay_delay_seconds": self.replay_delay_seconds,
                "game_type": GameType.to_string(self.game_type),
                "featured_mod": self.game_mode,
                "featured_mod_version": self.mod_version,
                "sim_mods": self.mods,
                "map_name": self.map_name,
                "map_file_path": self.map_file_path,    # "archive.ufo/Map Name/deadbeef"
                "host": self.host.login if self.host else "",
                "num_players": len(current_player_list),
                "max_players": self.max_players,
                "launched_at": self.launched_at,
                "rating_type": self.rating_type,
                "rating_min": self.displayed_rating_range.lo,
                "rating_max": self.displayed_rating_range.hi,
                "enforce_rating_range": self.enforce_rating_range,
                "galactic_war_planet_name": self.galactic_war_planet_name,
                "teams": {
                    k:v for k,v in {
                        team: [
                            player.login for player in current_player_list
                            if self.get_player_option(player.id, "Team") == team
                        ]
                        for team in list(self.teams)+[-1]  # playing teams + watchers
                    }.items()
                    if len(v)>0     # only teams with members
                }
            })
        return result

    @property
    def map_name(self):
        if self.map_file_path:
            map_name = self.map_file_path.split('/')[1]
        else:
            map_name = "SHERWOOD"
        return map_name

    def __eq__(self, other):
        if not isinstance(other, Game):
            return False
        else:
            return self.id == other.id

    def __hash__(self):
        return self.id.__hash__()

    def __str__(self) -> str:
        return (
            f"Game({self.id}, {self.host.login if self.host else ''}, "
            f"{self.map_file_path})"
        )
