from trueskill import Rating

from .rating_service import RatingService
from .config import config
from .core import Service
from pathlib import Path
from server.decorators import with_logger
from server.galactic_war import gml
from server.galactic_war.state import State, InvalidGalacticWarGame
from typing import Dict, List

from .galactic_war.planet import Planet
from .games.typedefs import EndedGameInfo
from .rating_service.typedefs import PlayerID


@with_logger
class GalacticWarService(Service):

    def __init__(self, rating_service: RatingService):
        rating_service.add_game_rating_callback(self.on_game_rating)
        self._state: State = self._load_state()
        self._dirty = False

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    def get_dirty(self):
        return self._dirty

    def set_dirty(self, dirty):
        self._dirty = dirty

    def on_game_rating(self, game_info: EndedGameInfo,
                       old_ratings: Dict[PlayerID, Rating],
                       new_ratings: Dict[PlayerID, Rating]):

        if game_info.galactic_war_planet_name is not None:
            try:
                self._state.validate_game(game_info)
                self._state.update_scores(game_info, old_ratings, new_ratings)
                self._state.update_front_lines(game_info.galactic_war_planet_name)
                self._state.capture_isolated_planets()
                uncaptured_capitals: List[Planet] = self._state.get_uncaptured_capitals()
                if len(uncaptured_capitals) < 2:
                    self._logger.info("[on_game_rating] the galaxy is captured by {}. starting a new scenario".format(
                        uncaptured_capitals[0] if len(uncaptured_capitals) > 0 else "no one"))
                    self._load_state(path=self.get_next_scenario())
                self._save_state()
                self._set_dirty(True)
            except InvalidGalacticWarGame as e:
                self._logger.error(f"[on_game_rating] {e}")

    def _get_next_scenario(self) -> Path:
        scenario_root = Path(config.GALACTIC_WAR_INITIAL_SCENARIO)
        scenario_files = [p for p in scenario_root.glob("*.gml")]
        scenario_files.sort(key=str)
        idx_scenario = [i for i, file in enumerate(scenario_files) if file == scenario_root / self._state.get_label()]
        if len(idx_scenario) == 0:
            return scenario_root / config.GALACTIC_WAR_INITIAL_SCENARIO

        idx_scenario = (idx_scenario[0] + 1) % len(scenario_files)
        return scenario_files[idx_scenario]

    def _load_state(self, path: str = None) -> State:
        if path is None:
            state_path = Path(config.GALACTIC_WAR_STATE_FILE)
        else:
            state_path = Path(path)

        if state_path.exists():
            self._logger.info(f"[_load_state] existing state: {state_path}")
            with state_path.open("rb") as fp:
                return State(gml.read_gml(fp))

        else:
            new_scenario_path = Path(config.GALACTIC_WAR_SCENARIO_PATH) / config.GALACTIC_WAR_INITIAL_SCENARIO
            self._logger.info(f"[_load_state] initial scenario: {new_scenario_path}")
            with new_scenario_path.open("rb") as fp:
                data = gml.read_gml(fp)
            with state_path.open("wb") as fp:
                gml.write_gml(data, fp)
            return State(data)

    def _save_state(self):
        state_path = Path(config.GALACTIC_WAR_STATE_FILE)
        self._logger.info(f"[_save_state] scenario={self._state.get_label()}, {state_path}")

        temp_state_path = state_path.with_suffix(".temp")
        with temp_state_path.open("wb") as fp:
            gml.write_gml(self._state.get_data(), fp)
        temp_state_path.replace(state_path)

