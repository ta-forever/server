import bisect
import dataclasses
import io
import json

import aiocron
import aiofiles
from trueskill import Rating

from .player_service import PlayerService
from .ladder_service import LadderService
from .game_service import GameService
from .db import FAFDatabase
from .factions import Faction
from .galactic_war.typedefs import GwGalaxyConfig
from .games.game_results import GameOutcome
from .rating_service import RatingService
from .config import config
from .core import Service
from pathlib import Path
from server.decorators import with_logger
from server.galactic_war import gml
from server.galactic_war.state import GalacticWarState, InvalidGalacticWarGame
from typing import Dict, List

from .galactic_war.planet import Planet
from .games.typedefs import EndedGameInfo, OutcomeLikelihoods, ValidityState, EndedGamePlayerSummary
from .rating_service.typedefs import PlayerID, TeamID, RankedRating
from .stats.achievement_service import AchievementService


@with_logger
class GalacticWarService(Service):

    def __init__(self, rating_service: RatingService, player_service: PlayerService, ladder_service: LadderService,
                 achievement_service: AchievementService, game_service: GameService, database: FAFDatabase):
        rating_service.add_game_rating_callback(self.on_game_rating)
        self.player_service = player_service
        self.ladder_service = ladder_service
        self.achievement_service = achievement_service
        self.game_service = game_service
        self.db = database
        self._state = {}        # keyed by mod technical name
        self._dirty = set()     # mod technical names that are dirty
        self._update_state_cron = None

    async def initialize(self):
        await self.reload_state()
        self.set_crontab()
        config.register_callback("GALACTIC_WAR_UPDATE_CRONTAB", self.set_crontab)
        config.register_callback("GALACTIC_WAR_GALAXIES", self.reload_state)
        config.register_callback("GALACTIC_WAR_RELOAD_STATE", self.reload_state)
        config.register_callback("GALACTIC_WAR_RESET", self.reset)
        config.register_callback("GALACTIC_WAR_MANUAL_CAPTURE", self.manual_capture)
        config.register_callback("GALACTIC_WAR_MANUAL_ATTACK", self.manual_attack)

    def set_crontab(self):
        self._logger.info(f"[set_crontab] setting galactic war update crontab to {config.GALACTIC_WAR_UPDATE_CRONTAB}")
        if self._update_state_cron is not None:
            self._update_state_cron.stop()
            self._update_state_cron = None

        if len(config.GALACTIC_WAR_UPDATE_CRONTAB) > 0:
            self._update_state_cron = aiocron.crontab(config.GALACTIC_WAR_UPDATE_CRONTAB, func=self.scheduled_update_state)

    async def reload_state(self):
        self._logger.info("[reload_state] reloading state from file ...")
        self._logger.info("   GALACTIC_WAR_GALAXIES:")
        self._logger.info(config.GALACTIC_WAR_GALAXIES)
        for galaxy_config in GwGalaxyConfig.from_dict_list(config.GALACTIC_WAR_GALAXIES).values():
            await self._load_state(galaxy_config)
            self.set_dirty(galaxy_config.technical_name, True)

    async def reset(self):
        self._logger.info(f"[reset] resetting ...")
        for galaxy_config in GwGalaxyConfig.from_dict_list(config.GALACTIC_WAR_GALAXIES).values():
            try:
                Path(galaxy_config.state_file).unlink()
            except FileNotFoundError:
                pass
            await self._load_state(galaxy_config)
            self.set_dirty(galaxy_config.technical_name, True)

    async def manual_capture(self):
        if not config.GALACTIC_WAR_MANUAL_CAPTURE:
            return

        try:
            galaxy_name = config.GALACTIC_WAR_MANUAL_CAPTURE["galaxy"]
            planet_name = config.GALACTIC_WAR_MANUAL_CAPTURE["planet"]
            faction_name = config.GALACTIC_WAR_MANUAL_CAPTURE["faction"]

            planet = None
            state = self._state[galaxy_name]
            if planet_name in state._planets_by_name.keys():
                planet = state._planets_by_name[planet_name]

            if planet is None:
                raise ValueError(f"unknown planet {galaxy_name}/{planet_name}")
            self._logger.info(f"[manual_capture] on {galaxy_name}/{planet_name} for {faction_name}")

            for faction in planet.get_ro_scores().keys():
                planet.set_score(faction, 100.0 if faction.name.lower() == faction_name.lower() else 0.0)

            galaxy_config = GwGalaxyConfig.from_dict_list(config.GALACTIC_WAR_GALAXIES).get(galaxy_name, None)
            if galaxy_config is None:
                self._logger.error(f"[manual_capture] unknown galaxy {galaxy_name}")

            await self._save_state(galaxy_config)
            self.set_dirty(planet.get_mod(), True)

        except Exception as e:
            self._logger.exception(e)

    async def manual_attack(self):
        if not config.GALACTIC_WAR_MANUAL_ATTACK:
            return

        try:
            galaxy_name, planet_name, pid1, fac1, rank1, pid2, fac2, rank2, pwin = [
                config.GALACTIC_WAR_MANUAL_ATTACK[k]
                for k in ["galaxy", "planet", "pid1", "faction1", "rank1", "pid2", "faction2", "rank2", "pwin"]
            ]
            pid1, pid2 = int(pid1), int(pid2)
            fac1, fac2 = Faction.from_string(fac1), Faction.from_string(fac2)
            rank1, rank2 = int(rank1), int(rank2)
            pwin = float(pwin)

            planet = None
            state = self._state[galaxy_name]
            if planet_name in state._planets_by_name.keys():
                planet = state._planets_by_name[planet_name]

            if planet is None:
                raise ValueError(f"unknown planet {galaxy_name}/{planet_name}")
            self._logger.info(f"[manual_attack] on planet={galaxy_name}/{planet_name}")

            game_outcome_1 = GameOutcome.VICTORY
            game_outcome_2 = GameOutcome.DEFEAT

            game_info = EndedGameInfo(
                game_id=0,
                rating_type='ranked',
                map_id=0,
                map_name=planet.get_map(),
                game_mode=planet.get_mod(),
                galactic_war_planet_name=f"{galaxy_name}/{planet_name}",
                mods=[],
                commander_kills={},
                validity=ValidityState.VALID,
                ended_game_player_summary=[
                    EndedGamePlayerSummary(player_id=pid1, team_id=1, faction=fac1, outcome=game_outcome_1),
                    EndedGamePlayerSummary(player_id=pid2, team_id=2, faction=fac2, outcome=game_outcome_2)
                    ]
            )

            old_ratings = {
                pid1: RankedRating(1500., 500., rank1, 1000),
                pid2: RankedRating(1500., 500., rank2, 1000)
            }

            team_outcome_likelihoods = {
                1: OutcomeLikelihoods(pwin, 0., 1.-pwin),
                2: OutcomeLikelihoods(1.-pwin, 0., pwin)
            }

            await self.on_game_rating(game_info, old_ratings, None, team_outcome_likelihoods)

        except Exception as e:
            self._logger.exception(e)

    async def shutdown(self):
        if self._update_state_cron is not None:
            self._update_state_cron.stop()
            self._update_state_cron = None

    def kill(self):
        if self._update_state_cron is not None:
            self._update_state_cron.stop()
            self._update_state_cron = None

    def get_dirty(self, galaxy_name: str) -> bool:
        return galaxy_name in self._dirty

    def get_dirties(self) -> set[str]:
        return set(self._dirty)

    def set_dirty(self, galaxy_name: str, dirty: bool):
        if dirty:
            self._dirty.add(galaxy_name)
        else:
            self._dirty.remove(galaxy_name)

    def clear_dirties(self):
        self._dirty.clear()

    async def on_game_rating(self, game_info: EndedGameInfo,
                             old_ratings: Dict[PlayerID, RankedRating],
                             new_ratings: Dict[PlayerID, Rating],
                             team_outcome_likelihoods: Dict[TeamID, OutcomeLikelihoods]):

        if game_info.galactic_war_planet_name is not None:

            planet_name = game_info.galactic_war_planet_name
            if '/' in planet_name:
                galaxy_name, planet_name = planet_name.split('/')
            else:
                galaxy_name = None
                for galaxy_name, state in self._state.items():
                    if planet_name in state._planets_by_name.keys():
                        break

            galaxy_config = GwGalaxyConfig.from_dict_list(config.GALACTIC_WAR_GALAXIES).get(galaxy_name, None)
            if galaxy_config is None:
                self._logger.error(f"[on_game_rating] unable to locate galaxy. planet={game_info.galactic_war_planet_name.lower()}")
                return
            game_info = game_info._replace(galactic_war_planet_name=planet_name)

            self._logger.info(f"[on_game_rating] game_id={game_info.game_id}, galaxy_name={galaxy_name}, planet={game_info.galactic_war_planet_name}")
            try:
                state = self._state[galaxy_name]
                state.validate_game(game_info)
                self._logger.info(f"[on_game_rating]   validated OK")

                old_scores = state._planets_by_name[game_info.galactic_war_planet_name].get_ro_scores()
                state.update_scores(game_info, old_ratings, new_ratings, team_outcome_likelihoods)
                new_scores = state._planets_by_name[game_info.galactic_war_planet_name].get_ro_scores()
                self._logger.info(f"[on_game_rating]    old_scores={old_scores}, new_scores={new_scores}")

                if config.GALACTIC_WAR_RANK_THRESHOLDS:
                    if galaxy_config.rank_avatar_ids:
                        await self._grant_avatars(galaxy_config.rank_avatar_ids, game_info, state)
                    if galaxy_config.rank_achievement_ids:
                        await self._grant_achievements(galaxy_config.rank_achievement_ids, game_info, state)

                if self._update_state_cron is None:
                    await self.update_state(galaxy_config)

                await self._save_state(galaxy_config)
                self.set_dirty(galaxy_name, True)

            except InvalidGalacticWarGame as e:
                self._logger.error(f"[on_game_rating] {e}")
                for player_info in game_info.ended_game_player_summary:
                    player = self.player_service.get_player(player_info.player_id)
                    if player:
                        await player.send_message({
                            "command": "notice",
                            "style": "info",
                            "text": f"Game {game_info.game_id} did not count towards Galactic War because: {str(e)}"})

    async def scheduled_update_state(self):
        for galaxy_config in GwGalaxyConfig.from_dict_list(config.GALACTIC_WAR_GALAXIES).values():
            changes_made = await self.update_state(galaxy_config)
            if changes_made > 0:
                await self._save_state(galaxy_config)
                self.set_dirty(galaxy_config.technical_name, True)

    async def update_state(self, galaxy_config: GwGalaxyConfig):
        self._logger.info(f"[update_state] updating {galaxy_config.technical_name} ...")
        state = self._state[galaxy_config.technical_name]

        state._data["dominance_threshold"] = config.GALACTIC_WAR_DOMINANCE_THRESHOLD

        front_line_changes = await state.update_front_lines(self.db)
        other_changes_made = 1
        while other_changes_made > 0:
            other_changes_made = state.capture_isolated_planets() + \
                                 state.capture_uncontested_planets()

        uncaptured_capitals: List[Planet] = state.get_capitals(standing=True, contested=True, captured=False)
        if len(uncaptured_capitals) < 2:
            self._logger.info("[update_state] the galaxy is captured by {}. starting a new scenario".format(
                uncaptured_capitals[0].get_capital_of().name if len(uncaptured_capitals) > 0 else "no one"))
            await self._load_state(galaxy_config, path=str(self._get_next_scenario(state.get_label())))
            self._initialise_scenario(galaxy_config)
            other_changes_made += 1

        return front_line_changes + other_changes_made

    async def on_command_set_map(self, player_id: int, galaxy_technical_name: str, planet_name: str, map_name: str):
        self._logger.info(f"[on_command_set_map] player_id={player_id} galaxy='{galaxy_technical_name}' planet='{planet_name}' map='{map_name}'")
        state = self._state[galaxy_technical_name]
        gw_config = GwGalaxyConfig.from_dict_list(config.GALACTIC_WAR_GALAXIES).get(galaxy_technical_name, None)
        if gw_config is None:
            raise ValueError(f"Galaxy {galaxy_technical_name} not found")

        allowed_maps_by_mod = {
            mod_name: state.get_map_pool(mod_name,
                                         self.ladder_service.queues,
                                         self.game_service.get_available_ranked_maps())
            for mod_name in gw_config.mods.keys()
        }
        state.on_command_set_map(player_id, planet_name, map_name, allowed_maps_by_mod)
        await self._save_state(gw_config)
        self.set_dirty(galaxy_technical_name, True)

    async def _grant_avatars(self, avatar_ids: Dict[Faction, List[int]], game_info: EndedGameInfo, state: GalacticWarState):
        for player_info in game_info.ended_game_player_summary:
            player_score = state.get_player_score(player_info.player_id, player_info.faction)
            metric = player_score.cum_winning_scores
            rank_tier = bisect.bisect_right(config.GALACTIC_WAR_RANK_THRESHOLDS, metric)
            try:
                avatar_id = avatar_ids[player_info.faction][rank_tier]
            except KeyError:
                self._logger.warn(f"[_grant_avatars] unable to find avatar_id for faction={player_info.faction} rank_tier={rank_tier} for player_id={player_info.player_id}")
                self._logger.debug(f"[_grant_avatars] GALACTIC_WAR_RANK_THRESHOLDS={config.GALACTIC_WAR_RANK_THRESHOLDS}")
                self._logger.debug(f"[_grant_avatars] avatar_ids={avatar_ids}")
                continue

            await self.ladder_service.grant_avatar(player_info.player_id, avatar_id, config.GALACTIC_WAR_RANK_AVATAR_AUTO_SELECT)

    async def _grant_achievements(self, achievement_ids: Dict[Faction, List[str]],
                                  game_info: EndedGameInfo, state: GalacticWarState):

        for player_info in game_info.ended_game_player_summary:
            player_score = state.get_player_score(player_info.player_id, player_info.faction)
            metric = player_score.cum_winning_scores
            rank_tier = bisect.bisect_right(config.GALACTIC_WAR_RANK_THRESHOLDS, metric)
            try:
                achievement_id = achievement_ids[player_info.faction][rank_tier]
            except KeyError:
                self._logger.warn(f"[_grant_avatars] unable to find achievement_id for faction={player_info.faction} rank_tier={rank_tier} for player_id={player_info.player_id}")
                self._logger.debug(f"[_grant_avatars] GALACTIC_WAR_RANK_THRESHOLDS={config.GALACTIC_WAR_RANK_THRESHOLDS}")
                self._logger.debug(f"[_grant_avatars] avatar_ids={achievement_ids}")
                continue
            queue = []
            self.achievement_service.unlock(achievement_id, queue)
            await self.achievement_service.execute_batch_update(player_info.player_id, queue)

    def _initialise_scenario(self, galaxy_config: GwGalaxyConfig):
        state = self._state[galaxy_config.technical_name]
        if len(state.get_capitals()) == 0:
            state.assign_two_capitals()
            state = GalacticWarState(state.get_data(), galaxy_config)
            self._state[galaxy_config.technical_name] = state

        if len(state.get_uncontested_planets()) == 2:
            self._logger.info("distributing planets")
            state.distribute_planets_to_factions()

        state.separate_abutting_factions()
        state.capture_uncontested_planets()

        allowed_maps_by_mod = {
            mod_name: state.get_map_pool(mod_name,
                                         self.ladder_service.queues,
                                         self.game_service.get_available_ranked_maps())
            for mod_name in galaxy_config.mods.keys()
        }
        state.ensure_allowed_maps(allowed_maps_by_mod)

    @staticmethod
    def _get_next_scenario(current_scenario_label: str) -> Path:
        scenario_root = Path(config.GALACTIC_WAR_SCENARIO_PATH)
        scenario_files = sorted(filter(lambda path: path.suffix in [".gml", ".json"], scenario_root.glob('*')))
        idx_scenario = [i for i, file in enumerate(scenario_files) if file == scenario_root / current_scenario_label]
        if len(idx_scenario) == 0:
            return scenario_root / config.GALACTIC_WAR_INITIAL_SCENARIO

        idx_scenario = (idx_scenario[0] + 1) % len(scenario_files)
        return scenario_files[idx_scenario]

    async def _load_state(self, galaxy_config: GwGalaxyConfig, path: str = None):
        if path is None:
            state_path = Path(galaxy_config.state_file)
        else:
            state_path = Path(path)

        if state_path.exists():
            self._logger.info(f"[_load_state] galaxy={galaxy_config.technical_name}. Loading existing state:{state_path}")
            self._state[galaxy_config.technical_name] = await self._do_load_state(galaxy_config, state_path)

        else:
            new_scenario_path = Path(config.GALACTIC_WAR_SCENARIO_PATH) / config.GALACTIC_WAR_INITIAL_SCENARIO
            self._logger.info(f"[_load_state] galaxy={galaxy_config.technical_name}. Loading scenario: {new_scenario_path}")
            self._state[galaxy_config.technical_name] = await self._do_load_state(galaxy_config, new_scenario_path)
            self._logger.info(f"[_load_state] galaxy={galaxy_config.technical_name}. Initialising scenario")
            self._initialise_scenario(galaxy_config)
            await self._save_state(galaxy_config)

    async def _save_state(self, galaxy_config: GwGalaxyConfig):
        state_path = Path(galaxy_config.state_file)
        self._logger.info(f"[_save_state] scenario={self._state[galaxy_config.technical_name].get_label()}, {state_path}")
        await self._do_save_state(state_path, self._state[galaxy_config.technical_name])

    @staticmethod
    async def _do_load_state(galaxy_config: GwGalaxyConfig, path: Path) -> GalacticWarState:
        if path.suffix == ".gml":
            async with aiofiles.open(path, "rb") as fp:
                contents = await fp.read()
            with io.BytesIO(contents) as fp:
                data = gml.read_gml(fp)

        elif path.suffix == ".json":
            async with aiofiles.open(path, "r") as fp:
                contents = await fp.read()
            data = json.loads(contents)

        else:
            raise ValueError(f"Unsupported Galactic War file type: {path}")

        return GalacticWarState(data, galaxy_config, Path(path).name)

    @staticmethod
    async def _do_save_state(path: Path, state: GalacticWarState):
        if path.suffix == ".json":
            temp_state_path = path.with_suffix(".temp")

            class DataclassJSONEncoder(json.JSONEncoder):
                def default(self, obj):
                    if dataclasses.is_dataclass(obj):
                        return dataclasses.asdict(obj)
                    return super().default(obj)

            contents = json.dumps(state.get_data(), indent=2, cls=DataclassJSONEncoder)
            async with aiofiles.open(temp_state_path, "w") as fp:
                await fp.write(contents)
            temp_state_path.replace(path)

        else:
            raise ValueError(f"Unsupported Galactic War file type: {path}")
