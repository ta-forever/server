import io
import json

import aiocron
import aiofiles
from trueskill import Rating

from . import PlayerService, LadderService
from .rating_service import RatingService
from .config import config
from .core import Service
from pathlib import Path
from server.decorators import with_logger
from server.galactic_war import gml
from server.galactic_war.state import GalacticWarState, InvalidGalacticWarGame
from typing import Dict, List

from .galactic_war.planet import Planet
from .games.typedefs import EndedGameInfo, OutcomeLikelihoods
from .rating_service.typedefs import PlayerID, TeamID, RankedRating


@with_logger
class GalacticWarService(Service):

    def __init__(self, rating_service: RatingService, player_service: PlayerService, ladder_service: LadderService):
        rating_service.add_game_rating_callback(self.on_game_rating)
        self.player_service = player_service
        self.ladder_service = ladder_service
        self._state = None
        self._dirty = False
        self._update_state_cron = None

    async def initialize(self):
        for mod in
        await self._load_state()
        self.set_dirty(True)
        self.set_crontab()
        config.register_callback("GALACTIC_WAR_UPDATE_CRONTAB", self.set_crontab)
        config.register_callback("GALACTIC_WAR_RELOAD_STATE", self.reload_state)
        config.register_callback("GALACTIC_WAR_RESET", self.reset)
        config.register_callback("GALACTIC_WAR_MANUAL_CAPTURE", self.manual_capture)

    def set_crontab(self):
        self._logger.info(f"[set_crontab] setting galactic war update crontab to {config.GALACTIC_WAR_UPDATE_CRONTAB}")
        if self._update_state_cron is not None:
            self._update_state_cron.stop()
            self._update_state_cron = None

        if len(config.GALACTIC_WAR_UPDATE_CRONTAB) > 0:
            self._update_state_cron = aiocron.crontab(config.GALACTIC_WAR_UPDATE_CRONTAB, func=self.scheduled_update_state)

    async def reload_state(self):
        self._logger.info("[reload_state] reloading state from file ...")
        await self._load_state()
        self.set_dirty(True)

    async def reset(self):
        self._logger.info(f"[reset] resetting ...")
        try:
            Path(config.GALACTIC_WAR_STATE_FILE).unlink()
        except FileNotFoundError:
            pass
        await self._load_state()
        self.set_dirty(True)

    async def manual_capture(self):
        try:
            for capture in config.GALACTIC_WAR_MANUAL_CAPTURE.split(";"):
                planet_name, faction_name = capture.split(':')
                self._logger.info(f"[manual_capture] capturing {planet_name} for {faction_name}")
                planet = self._state._planets_by_name[planet_name]
                for faction in planet.get_ro_scores().keys():
                    planet.set_score(faction, 100.0 if faction.name.lower() == faction_name.lower() else 0.0)
            await self._save_state()
            self.set_dirty(True)

        except Exception as e:
            self._logger.warn(f"unable to capture planet: {e}")

    def shutdown(self):
        if self._update_state_cron is not None:
            self._update_state_cron.stop()
            self._update_state_cron = None

    def kill(self):
        if self._update_state_cron is not None:
            self._update_state_cron.stop()
            self._update_state_cron = None

    def get_dirty(self):
        return self._dirty

    def set_dirty(self, dirty):
        self._dirty = dirty

    async def on_game_rating(self, game_info: EndedGameInfo,
                             old_ratings: Dict[PlayerID, RankedRating],
                             new_ratings: Dict[PlayerID, Rating],
                             team_outcome_likelihoods: Dict[TeamID, OutcomeLikelihoods]):

        if game_info.galactic_war_planet_name is not None:
            self._logger.info(f"[on_game_rating] game_id={game_info.game_id}, planet={game_info.galactic_war_planet_name}")
            try:
                self._state.validate_game(game_info)
                self._logger.info(f"[on_game_rating] game_id={game_info.game_id} validated OK")

                old_scores = self._state._planets_by_name[game_info.galactic_war_planet_name].get_ro_scores()
                self._state.update_scores(game_info, old_ratings, new_ratings, team_outcome_likelihoods)
                new_scores = self._state._planets_by_name[game_info.galactic_war_planet_name].get_ro_scores()
                self._logger.info(f"[update_scores] game_id={game_info.game_id}, planet={game_info.galactic_war_planet_name}, old_scores={old_scores}, new_scores={new_scores}")

                if self._update_state_cron is None:
                    await self.update_state()

                await self._save_state()
                self.set_dirty(True)

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
        changes_made = await self.update_state()
        if changes_made > 0:
            await self._save_state()
            self.set_dirty(True)

    async def update_state(self):
        self._logger.info(f"[update_state] processing ...")
        front_line_changes = self._state.update_front_lines()
        other_changes_made = 1
        while other_changes_made > 0:
            other_changes_made = self._state.capture_isolated_planets() + \
                                 self._state.capture_uncontested_planets()

        uncaptured_capitals: List[Planet] = self._state.get_capitals(standing=True, contested=True, captured=False)
        if len(uncaptured_capitals) < 2:
            self._logger.info("[update_state] the galaxy is captured by {}. starting a new scenario".format(
                uncaptured_capitals[0].get_capital_of().name if len(uncaptured_capitals) > 0 else "no one"))
            await self._load_state(path=str(self._get_next_scenario()))
            self._initialise_scenario()
            other_changes_made += 1

        return front_line_changes + other_changes_made

    def _initialise_scenario(self):
        changes_made = 0

        if len(self._state.get_capitals()) == 0:
            self._state.assign_two_capitals()
            self._state = GalacticWarState(self._state.get_data())
            changes_made += 1

        if len(self._state.get_uncontested_planets()) == 2:
            self._logger.info("distributing planets")
            self._state.distribute_planets_to_factions()
            changes_made += 1

        self._state.seperate_abutting_factions()
        self._state.capture_uncontested_planets()
        if config.GALACTIC_WAR_INITIALISE_ENSURE_RANKED_MAPS:
            self._state.ensure_ranked_maps(self.ladder_service.queues)

        return changes_made

    def _get_next_scenario(self) -> Path:
        scenario_root = Path(config.GALACTIC_WAR_SCENARIO_PATH)
        scenario_files = sorted(filter(lambda path: path.suffix in [".gml", ".json"], scenario_root.glob('*')))
        idx_scenario = [i for i, file in enumerate(scenario_files) if file == scenario_root / self._state.get_label()]
        if len(idx_scenario) == 0:
            return scenario_root / config.GALACTIC_WAR_INITIAL_SCENARIO

        idx_scenario = (idx_scenario[0] + 1) % len(scenario_files)
        return scenario_files[idx_scenario]

    async def _load_state(self, path: str = None) -> None:
        if path is None:
            state_path = Path(config.GALACTIC_WAR_STATE_FILE)
        else:
            state_path = Path(path)

        if state_path.exists():
            self._logger.info(f"[_load_state] existing state: {state_path}")
            self._state = await self._do_load_state(state_path)

        else:
            new_scenario_path = Path(config.GALACTIC_WAR_SCENARIO_PATH) / config.GALACTIC_WAR_INITIAL_SCENARIO
            self._logger.info(f"[_load_state] initial scenario: {new_scenario_path}")
            self._state = await self._do_load_state(new_scenario_path)
            self._initialise_scenario()
            await self._save_state()

    async def _save_state(self):
        state_path = Path(config.GALACTIC_WAR_STATE_FILE)
        self._logger.info(f"[_save_state] scenario={self._state.get_label()}, {state_path}")
        await self._do_save_state(state_path, self._state)

    @staticmethod
    async def _do_load_state(path: Path) -> GalacticWarState:
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

        return GalacticWarState(data, Path(path).name)

    @staticmethod
    async def _do_save_state(path: Path, state: GalacticWarState):
        if path.suffix == ".json":
            temp_state_path = path.with_suffix(".temp")
            contents = json.dumps(state.get_data(), indent=2)
            async with aiofiles.open(temp_state_path, "w") as fp:
                await fp.write(contents)
            temp_state_path.replace(path)

        else:
            raise ValueError(f"Unsupported Galactic War file type: {path}")
