from collections import Counter
from typing import Dict, List, Optional, Type, Union, ValuesView

import aiocron
import glob
import json
import os
import shutil
import sqlalchemy.sql

from server.config import config

from . import metrics
from .core import Service
from .db import FAFDatabase
from .decorators import with_logger
from .games import (
    CoopGame,
    CustomGame,
    FeaturedMod,
    FeaturedModType,
    Game,
    GameState,
    LadderGame,
    ValidityState,
    VisibilityState
)
from .games.typedefs import EndedGameInfo, ReplayInfo
from .matchmaker import MatchmakerQueue
from .message_queue_service import MessageQueueService
from .players import Player
from .rating_service import RatingService
from .galactic_war_service import GalacticWarService


@with_logger
class GameService(Service):
    """
    Utility class for maintaining lifecycle of games
    """

    def __init__(
            self,
            database: FAFDatabase,
            player_service,
            game_stats_service,
            rating_service: RatingService,
            message_queue_service: MessageQueueService,
            galactic_war_service: GalacticWarService
    ):
        self._db = database
        self._dirty_games = set()
        self._dirty_queues = set()
        self.player_service = player_service
        self.game_stats_service = game_stats_service
        self.galactic_war_service = galactic_war_service
        self._rating_service = rating_service
        self._message_queue_service = message_queue_service
        self.game_id_counter = 0
        self._available_matchmaker_queues: Dict[str,MatchmakerQueue] = {} # updated by ladder_service

        # Populated below in really_update_static_ish_data.
        self.featured_mods = dict()

        # A set of mod ids that are allowed in ranked games (everyone loves caching)
        self.ranked_mods = set()

        # The set of active games
        self._games: Dict[int, Game] = dict()

    def get_archive_dir_for_game_id(self, replay_id: int):
        replays_path = "/content/replays"
        mm = replay_id // 100000000
        nn = (replay_id // 1000000) % 100
        oo = (replay_id // 10000) % 100
        pp = (replay_id // 100) % 100
        return f"{replays_path}/{mm}/{nn}/{oo}/{pp}"

    async def initialize(self) -> None:
        await self.initialise_game_counter()
        await self.update_data()
        self._update_cron = aiocron.crontab("*/10 * * * *", func=self.update_data)
        self._archive_replays_cron = aiocron.crontab("* * * * *", func=self.archive_new_replays)
        self._process_replay_metadata = aiocron.crontab("* * * * *", func=self.process_replay_metadata)
        await self._message_queue_service.declare_exchange(config.MQ_EXCHANGE_NAME)

    async def initialise_game_counter(self):
        async with self._db.acquire() as conn:
            # InnoDB, unusually, doesn't allow insertion of values greater than the next expected
            # value into an auto_increment field. We'd like to do that, because we no longer insert
            # games into the database when they don't start, so game ids aren't contiguous (as
            # unstarted games consume ids that never get written out).
            # So, id has to just be an integer primary key, no auto-increment: we handle its
            # incrementing here in game service, but have to do this slightly expensive query on
            # startup (though the primary key index probably makes it super fast anyway).
            # This is definitely a better choice than inserting useless rows when games are created,
            # doing LAST_UPDATE_ID to get the id number, and then doing an UPDATE when the actual
            # data to go into the row becomes available: we now only do a single insert for each
            # game, and don't end up with 800,000 junk rows in the database.
            result = await conn.execute("SELECT MAX(id) FROM game_stats")
            row = await result.fetchone()
            self.game_id_counter = row[0] or 0

    async def update_data(self):
        """
        Loads from the database the mostly-constant things that it doesn't make sense to query every
        time we need, but which can in principle change over time.
        """
        async with self._db.acquire() as conn:
            result = await conn.execute(
                "SELECT `id`, `gamemod`, `name`, description, publish, `order` FROM game_featuredMods")

            async for row in result:
                mod_id, name, full_name, description, publish, order = (row[i] for i in range(6))
                self.featured_mods[name] = FeaturedMod(
                    mod_id, name, full_name, description, publish, order)

            result = await conn.execute("SELECT uid FROM table_mod WHERE ranked = 1")
            rows = await result.fetchall()

            # Turn resultset into a list of uids
            self.ranked_mods = set(map(lambda x: x[0], rows))

    async def archive_new_replays(self):
        """
        looks for /content/replays/mmnnooppqq.tad and archive them into /content/replays/mm/nn/oo/pp/mmnnooppqq.tad
        """
        replays_path = "/content/replays"
        for file_path in glob.glob(f"{replays_path}/*.tad"):
            file_name = os.path.basename(file_path)
            game_id = int(os.path.splitext(file_name)[0])
            archive_dir = self.get_archive_dir_for_game_id(game_id)

            self._logger.info("[archive_new_replays] archiving replay %s to %s", file_path, archive_dir)
            os.makedirs(archive_dir, exist_ok=True)
            shutil.make_archive(os.path.join(archive_dir, str(game_id)), "zip", replays_path, f"{game_id}.tad")
            os.remove(file_path)

            async with self._db.acquire() as conn:
                await conn.execute(sqlalchemy.sql.text(
                    "UPDATE `game_stats` SET `game_stats`.`replay_available` = 1 WHERE `game_stats`.`id` = :game_id"),
                    game_id=game_id)

    async def process_replay_metadata(self):
        """
        Looks for /content/replays/*.json and processes the meta data recorded in there by the demo compiler.
        It informs TAF about map and mod hashes so they can be used to install the correct map and mod versions
        when users later want to watch replays
        :return:
        """
        replays_path = "/content/replays"
        for file_path in glob.glob(f"{replays_path}/*.json"):
            self._logger.info("[process_replay_metadata] processing metadata for %s", file_path)
            with open(file_path, "rb") as fp:
                file_content = fp.read()
                data = json.loads(file_content)
                file_content = file_content.decode("utf-8")

            game_id = data.get("gameId")
            ta_version = "{}.{}".format(data.get("taVersionMajor"), data.get("taVersionMinor"))
            units_hash = data.get("unitsHash")
            map_hash = data.get("taMapHash")

            async with self._db.acquire() as conn:
                result = await conn.execute(sqlalchemy.sql.text(
                    "SELECT `gameMod`, `mapId` from `game_stats` WHERE id = :game_id"), game_id=game_id)
                row = await result.fetchone()
                if row is None:
                    if game_id not in self._games:
                        self._logger.info(
                            f"[process_replay_metadata] ditching {file_path} because game_id {game_id} not known")
                        os.remove(file_path)
                        return
                    else:
                        # try again later
                        continue

                await conn.execute(sqlalchemy.sql.text(
                    "UPDATE `game_stats` SET replay_meta = :replay_meta WHERE id = :game_id"),
                    replay_meta=file_content, game_id=game_id)

                if row[1] is None:
                    os.rename(file_path, file_path + ".unknown_map")
                    self._logger.info(
                        f"[process_replay_metadata] ditching {file_path} because row[1] is None (unknown map)")
                    continue
                else:
                    os.remove(file_path)

                featured_mod_id = int(row[0])
                map_version_id = int(row[1])
                self._logger.info(
                    f"[process_replay_metadata] game_id={game_id}, ta_version={ta_version}, units_hash={units_hash}, map_hash={map_hash}, featured_mod_id={featured_mod_id}, map_version_id={map_version_id}")

                sql = sqlalchemy.sql.text("""
                    INSERT INTO `game_featuredMods_version` (`game_featuredMods_id`, `version`, `ta_hash`, `observation_count`)
                    VALUES (:featured_mod_id, :ta_version, :units_hash, 1)
                    ON DUPLICATE KEY UPDATE observation_count = observation_count+1
                    """)
                await conn.execute(sql, featured_mod_id=featured_mod_id, ta_version=ta_version, units_hash=units_hash)

                sql = sqlalchemy.sql.text("UPDATE `map_version` SET ta_hash = :map_hash WHERE id = :map_version_id")
                await conn.execute(sql, map_hash=map_hash, map_version_id=map_version_id)

    async def get_replay_info(self, db_connection, game_id: int):
        result = await db_connection.execute(sqlalchemy.sql.text("""
            SELECT replay_meta, tada_available, startTime, game_featuredMods.file_extension
            FROM `game_stats`
            JOIN `game_featuredMods` on game_featuredMods.id = game_stats.gameMod
            WHERE game_stats.id = :game_id
            """), game_id=game_id)
        row = await result.fetchone()
        if row is None:
            raise ValueError(f"Unable to find any information about replay id={game_id}")
        replay_meta = json.loads(row[0]) if row[0] is not None else None
        replay_meta["datestamp"] = row[2].date().isoformat()
        replay_meta["file_extension"] = row[3]
        return ReplayInfo(replay_meta=replay_meta, tada_available=row[1])

    async def set_game_tada_available(self, db_connection, game_id: int, available: bool):
        available = 1 if available else 0
        await db_connection.execute(sqlalchemy.sql.text(
            "UPDATE `game_stats` SET `tada_available`= :available WHERE id = :game_id"), available=available, game_id=game_id)

    def set_available_matchmaker_queues(self, queues: Dict[str,MatchmakerQueue]):
        self._available_matchmaker_queues = queues

    def get_available_matchmaker_queues(self) -> Dict[str,MatchmakerQueue]:
        return self._available_matchmaker_queues

    @property
    def dirty_games(self):
        return self._dirty_games

    @property
    def dirty_queues(self):
        return self._dirty_queues

    def mark_dirty(self, obj: Union[Game, MatchmakerQueue]):
        if isinstance(obj, Game):
            self._dirty_games.add(obj)
        elif isinstance(obj, MatchmakerQueue):
            self._dirty_queues.add(obj)

    def clear_dirty(self):
        self._dirty_games = set()
        self._dirty_queues = set()

    def create_uid(self) -> int:
        self.game_id_counter += 1

        return self.game_id_counter

    def create_game(
            self,
            game_mode: str,
            mod_version: str,
            game_class: Type[Game] = None,
            visibility=VisibilityState.PUBLIC,
            host: Optional[Player] = None,
            name: Optional[str] = None,
            mapname: Optional[str] = None,
            password: Optional[str] = None,
            matchmaker_queue_id: Optional[int] = None,
            **kwargs
    ):
        """
        Main entrypoint for creating new games
        """
        game_id = self.create_uid()
        game_args = {
            "database": self._db,
            "id_": game_id,
            "host": host,
            "name": name,
            "map_": mapname,
            "game_mode": game_mode,
            "mod_version": mod_version,
            "game_service": self,
            "game_stats_service": self.game_stats_service,
            "matchmaker_queue_id": matchmaker_queue_id
        }
        game_args.update(kwargs)

        if not game_class:
            game_class = {
                FeaturedModType.LADDER_1V1: LadderGame,
                FeaturedModType.COOP: CoopGame,
                FeaturedModType.FAF: CustomGame,
                FeaturedModType.FAFBETA: CustomGame,
                FeaturedModType.EQUILIBRIUM: CustomGame
            }.get(game_mode, Game)

        self._logger.info("[create_game] game_class=%s, game_args=%s", repr(game_class), repr(game_args))
        game = game_class(**game_args)

        self._games[game_id] = game

        game.visibility = visibility
        game.password = password

        self.mark_dirty(game)
        return game

    def update_active_game_metrics(self):
        modes = list(self.featured_mods.keys())

        game_counter = Counter(
            (
                game.game_mode if game.game_mode in modes else "other",
                game.state
            )
            for game in self._games.values()
        )

        for state in GameState:
            for mode in modes + ["other"]:
                metrics.active_games.labels(mode, state.name).set(
                    game_counter[(mode, state)]
                )

    @property
    def live_games(self) -> List[Game]:
        return [game for game in self._games.values()
                if game.state in (GameState.LAUNCHING, GameState.LIVE)]

    @property
    def open_games(self) -> List[Game]:
        """
        Return all games that are STAGING, BATTLEROOM, LAUNCHING or LIVE
        :return:
        """
        return [game for game in self._games.values()
                if game.state in (GameState.STAGING, GameState.BATTLEROOM, GameState.LAUNCHING, GameState.LIVE)]

    @property
    def all_games(self) -> ValuesView[Game]:
        return self._games.values()

    @property
    def pending_games(self) -> List[Game]:
        return [game for game in self._games.values()
                if game.state in (GameState.INITIALIZING, GameState.STAGING, GameState.BATTLEROOM, GameState.LAUNCHING)]

    def remove_game(self, game: Game):
        if game.id in self._games:
            del self._games[game.id]

    def __getitem__(self, item: int) -> Game:
        return self._games[item]

    def __contains__(self, item):
        return item in self._games

    async def publish_game_results(self, game_results: EndedGameInfo):
        result_dict = game_results.to_dict()
        await self._message_queue_service.publish(
            config.MQ_EXCHANGE_NAME,
            "success.gameResults.create",
            result_dict,
        )

        # TODO: Remove when rating service starts listening to message queue
        if game_results.validity is ValidityState.VALID and game_results.rating_type is not None:
            await self._rating_service.enqueue(game_results)
