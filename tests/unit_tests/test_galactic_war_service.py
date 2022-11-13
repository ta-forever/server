import asyncio
from pathlib import Path

import pytest
import trueskill
from mock import AsyncMock
from trueskill import Rating

from server import GalacticWarService, config
from server.factions import Faction
from server.galactic_war.planet import Planet
from server.galactic_war.state import InvalidGalacticWarGame, GalacticWarState
from server.games.game_results import GameOutcome
from server.games.typedefs import EndedGameInfo, ValidityState, EndedGamePlayerSummary, OutcomeLikelihoods
from server.matchmaker import MatchmakerQueue, MapPool
from server.rating import RatingType
from server.rating_service.typedefs import RankedRating
from server.types import Map

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def mock_ladder_service():

    class MockLadderService:
        def __init__(self):
            self.queues = {
                "ladder1v1_tacc",
                MatchmakerQueue(None, None, "ladder1v1_tacc", 0, "tacc", "tacc_1v1", 1, [(
                    MapPool(0, "tacc_1v1", [
                        Map(0, "SHERWOOD", "total2.hpi/SHERWOOD:1234abcd", 1)
                    ]),
                    None, None
                )])
            }
    yield MockLadderService()


@pytest.fixture
async def galactic_war_service(rating_service, player_service, mock_ladder_service):
    config.GALACTIC_WAR_STATE_FILE = "tests/gw_state.json"
    config.GALACTIC_WAR_SCENARIO_PATH = "tests/data/gw_scenarios"
    config.GALACTIC_WAR_INITIAL_SCENARIO = "scenario_0.gml"
    config.GALACTIC_WAR_UPDATE_CRONTAB = ""
    config.GALACTIC_WAR_INITIALISE_ENSURE_RANKED_MAPS = False
    config.GALACTIC_WAR_MAX_SCORE = 20.
    try:
        Path(config.GALACTIC_WAR_STATE_FILE).unlink()
    except IOError:
        pass

    service = GalacticWarService(rating_service, player_service, mock_ladder_service)
    await service.initialize()
    yield service
    service.kill()


@pytest.fixture
async def reloaded_galactic_war_service(rating_service, player_service, mock_ladder_service):
    config.GALACTIC_WAR_STATE_FILE = "tests/gw_state.json"
    config.GALACTIC_WAR_SCENARIO_PATH = "tests/data/gw_scenarios"
    config.GALACTIC_WAR_INITIAL_SCENARIO = "scenario_0.gml"
    config.GALACTIC_WAR_UPDATE_CRONTAB = ""
    config.GALACTIC_WAR_INITIALISE_ENSURE_RANKED_MAPS = False
    config.GALACTIC_WAR_MAX_SCORE = 20.
    service = GalacticWarService(rating_service, player_service, mock_ladder_service)
    await service.initialize()
    yield service
    service.kill()


@pytest.fixture
async def periodic_update_galactic_war_service(rating_service, player_service, mock_ladder_service):
    config.GALACTIC_WAR_STATE_FILE = "tests/gw_state.json"
    config.GALACTIC_WAR_SCENARIO_PATH = "tests/data/gw_scenarios"
    config.GALACTIC_WAR_INITIAL_SCENARIO = "scenario_0.gml"
    config.GALACTIC_WAR_UPDATE_CRONTAB = "* * * * * *"
    config.GALACTIC_WAR_INITIALISE_ENSURE_RANKED_MAPS = False
    config.GALACTIC_WAR_MAX_SCORE = 20.
    try:
        Path(config.GALACTIC_WAR_STATE_FILE).unlink()
    except IOError:
        pass

    service = GalacticWarService(rating_service, player_service, mock_ladder_service)
    await service.initialize()
    yield service
    service.kill()


@pytest.fixture
def game_info():
    return EndedGameInfo(
        1,
        RatingType.TEST_LADDER,
        1, "[V] Crimson Bay",
        "taesc",
        "Thalassean",
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 1, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(3, 2, Faction.arm, GameOutcome.DEFEAT),
            EndedGamePlayerSummary(4, 2, Faction.arm, GameOutcome.DEFEAT),
        ],
    )


@pytest.fixture
def game_info_mixed_factions():
    return EndedGameInfo(
        1,
        RatingType.TEST_LADDER,
        1, "[V] Crimson Bay",
        "taesc",
        "Thalassean",
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.arm, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 1, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(3, 2, Faction.arm, GameOutcome.DEFEAT),
            EndedGamePlayerSummary(4, 2, Faction.core, GameOutcome.DEFEAT),
        ],
    )


@pytest.fixture
def game_info_all_arm():
    return EndedGameInfo(
        1,
        RatingType.TEST_LADDER,
        1, "[V] Crimson Bay",
        "taesc",
        "Thalassean",
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.arm, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 1, Faction.arm, GameOutcome.VICTORY),
            EndedGamePlayerSummary(3, 2, Faction.arm, GameOutcome.DEFEAT),
            EndedGamePlayerSummary(4, 2, Faction.arm, GameOutcome.DEFEAT),
        ],
    )


@pytest.fixture
def game_info_three_teams():
    return EndedGameInfo(
        1,
        RatingType.TEST_LADDER,
        1, "[V] Crimson Bay",
        "taesc",
        "Thalassean",
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.gok, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 2, Faction.core, GameOutcome.DEFEAT),
            EndedGamePlayerSummary(3, 3, Faction.arm, GameOutcome.DEFEAT)
        ],
    )


@pytest.fixture
def game_info_non_contested_planet():
    return EndedGameInfo(
        1,
        RatingType.TEST_LADDER,
        1, "[Pro] Lava Run",
        "tavmod",
        "Gelidus",
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(3, 2, Faction.arm, GameOutcome.DEFEAT),
        ],
    )


@pytest.fixture
def game_info_bugged_update():
    return EndedGameInfo(
        13733,
        'ladder1v1_tavmod',
        2447, '[Pro] Comet Catcher',
        "tavmod",
        "Dump",
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 0, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 1, Faction.arm, GameOutcome.DEFEAT),
        ],
    )


async def test_validate_not_contested(galactic_war_service, game_info_non_contested_planet):
    service = galactic_war_service
    game_info = game_info_non_contested_planet
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info)


async def test_load_initial_scenario(galactic_war_service):
    service = galactic_war_service
    assert(len(service._state.get_data()) > 0)
    assert(len(service._state.get_label()) > 0)
    assert(Path(config.GALACTIC_WAR_STATE_FILE).exists())


async def test_validate_valid_game(galactic_war_service, game_info):
    service = galactic_war_service
    service._state.validate_game(game_info)


async def test_validate_bad_planet(galactic_war_service, game_info):
    service = galactic_war_service
    game_info = game_info._replace(galactic_war_planet_name="some random planet")
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info)


async def test_validate_bad_map(galactic_war_service, game_info):
    service = galactic_war_service
    game_info = game_info._replace(map_name="some random map")
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info)


async def test_validate_bad_mod(galactic_war_service, game_info):
    service = galactic_war_service
    game_info = game_info._replace(game_mode="some random mod")
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info)


async def test_validate_mixed_factions(galactic_war_service, game_info_mixed_factions):
    service = galactic_war_service
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info_mixed_factions)


async def test_validate_not_opposing_factions(galactic_war_service, game_info_all_arm):
    service = galactic_war_service
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info_all_arm)


async def test_validate_bad_teams(galactic_war_service, game_info_three_teams):
    service = galactic_war_service
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info_three_teams)


async def test_validate_not_ranked(galactic_war_service, game_info):
    service = galactic_war_service
    game_info = game_info._replace(rating_type=RatingType.GLOBAL)
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info)


async def test_validate_bad_validity_state(galactic_war_service, game_info):
    service = galactic_war_service
    game_info = game_info._replace(validity=ValidityState.CHEATS_ENABLED)
    with pytest.raises(InvalidGalacticWarGame):
        service._state.validate_game(game_info)


async def test_process_game_still_contested(galactic_war_service, game_info):
    service = galactic_war_service
    old_ratings = {
        1: RankedRating(1000., 10., 1, 100),
        2: RankedRating(1000., 10., 4, 100),
        3: RankedRating(1000., 10., 2, 100),
        4: RankedRating(1000., 10., 3, 100)
    }
    new_ratings = {
        1: Rating(1001., 10.),
        2: Rating(1001., 10.),
        3: Rating(999., 10.),
        4: Rating(999., 10.)
    }
    team_outcome_likelihoods = {
        1: OutcomeLikelihoods(0.45, 0.1, 0.45),
        2: OutcomeLikelihoods(0.45, 0.1, 0.45),
    }

    assert(~service.get_dirty())
    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() == Faction.arm)

    await service.on_game_rating(game_info, old_ratings, new_ratings, team_outcome_likelihoods)

    assert(service.get_dirty())
    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Thalassean"].get_belligerent_score(1, Faction.core) > 0.)
    assert(service._state._planets_by_name["Thalassean"].get_belligerent_score(2, Faction.core) > 0.)
    assert(service._state._planets_by_name["Thalassean"].get_belligerent_score(3, Faction.arm) < 0.)
    assert(service._state._planets_by_name["Thalassean"].get_belligerent_score(4, Faction.arm) < 0.)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() == Faction.arm)


async def test_process_game_captured(galactic_war_service, game_info):
    service = galactic_war_service
    old_ratings = {
        1: RankedRating(100., 10., 98, 100),
        2: RankedRating(10., 10., 99, 100),
        3: RankedRating(2000., 10., 0, 100),
        4: RankedRating(1900., 10., 1, 100)
    }
    new_ratings = {
        1: Rating(1100., 10.),
        2: Rating(1100., 10.),
        3: Rating(900., 10.),
        4: Rating(900., 10.)
    }
    team_outcome_likelihoods = {
        1: OutcomeLikelihoods(0.01, 0., 0.99),
        2: OutcomeLikelihoods(0.99, 0., 0.01),
    }

    assert(~service.get_dirty())
    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() == Faction.arm)

    await service.on_game_rating(game_info, old_ratings, new_ratings, team_outcome_likelihoods)

    assert(service.get_dirty())
    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() == Faction.core)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() is None)

    saved_state = await service._do_load_state(Path(config.GALACTIC_WAR_STATE_FILE))
    assert(saved_state._planets_by_name["Thalassean"].get_controlled_by() == Faction.core)
    assert(saved_state._planets_by_name["Gelidus"].get_controlled_by() is None)


async def test_process_capture_isolated_planets(galactic_war_service):
    service = galactic_war_service
    service._state._planets_by_name["Thalassean"].set_controlled_by(Faction.arm)
    service._state._planets_by_name["Barathrum"].set_controlled_by(Faction.arm)
    service._state._planets_by_name["Lusch"].set_controlled_by(Faction.arm)
    service._state._planets_by_name["Gelidus"].set_controlled_by(None)
    service._state._planets_by_name["Gelidus"].reset_scores()
    service._state._planets_by_name["Dump"].set_controlled_by(None)
    service._state._planets_by_name["Dump"].reset_scores()
    service._state._planets_by_name["Rougpelt"].set_controlled_by(None)
    service._state._planets_by_name["Rougpelt"].reset_scores()

    await service.update_state()

    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() == Faction.core)
    assert(service._state._planets_by_name["Barathrum"].get_controlled_by() == Faction.core)
    assert(service._state._planets_by_name["Lusch"].get_controlled_by() == Faction.core)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Dump"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Rougpelt"].get_controlled_by() is None)


async def test_process_capture_uncontested_planets(galactic_war_service):
    service = galactic_war_service
    service._state._planets_by_name["Thalassean"].set_controlled_by(Faction.arm)
    service._state._planets_by_name["Barathrum"].set_controlled_by(Faction.arm)
    service._state._planets_by_name["Lusch"].set_controlled_by(Faction.arm)
    service._state._planets_by_name["Gelidus"].set_controlled_by(Faction.arm)
    service._state._planets_by_name["Dump"].set_controlled_by(None)
    service._state._planets_by_name["Dump"].reset_scores()
    service._state._planets_by_name["Rougpelt"].set_controlled_by(Faction.arm)

    await service.update_state()

    assert(service._state._planets_by_name["Dump"].get_controlled_by() == Faction.arm)


async def test_end_scenario(galactic_war_service):
    service = galactic_war_service
    service._load_state = AsyncMock()
    service._state._planets_by_name["Empyrrean"].set_controlled_by(Faction.core)
    service._state._planets_by_name["Dump"].set_controlled_by(Faction.core)

    await service.update_state()

    service._load_state.assert_awaited_once()


async def test_periodic_update(periodic_update_galactic_war_service, game_info):
    service = periodic_update_galactic_war_service
    old_ratings = {
        1: RankedRating(100., 10., 98, 100),
        2: RankedRating(10., 10., 99, 100),
        3: RankedRating(2000., 10., 0, 100),
        4: RankedRating(1900., 10., 1, 100)
    }
    new_ratings = {
        1: Rating(1100., 10.),
        2: Rating(1100., 10.),
        3: Rating(900., 10.),
        4: Rating(900., 10.)
    }
    team_outcome_likelihoods = {
        1: OutcomeLikelihoods(0.01, 0., 0.99),
        2: OutcomeLikelihoods(0.99, 0., 0.01),
    }

    assert(~service.get_dirty())
    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() == Faction.arm)

    await service.on_game_rating(game_info, old_ratings, new_ratings, team_outcome_likelihoods)
    assert(service.get_dirty())
    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() == Faction.arm)

    await asyncio.sleep(2)
    assert(service._state._planets_by_name["Thalassean"].get_controlled_by() == Faction.core)
    assert(service._state._planets_by_name["Gelidus"].get_controlled_by() is None)

    saved_state = await service._do_load_state(Path(config.GALACTIC_WAR_STATE_FILE))
    assert(saved_state._planets_by_name["Thalassean"].get_controlled_by() == Faction.core)
    assert(saved_state._planets_by_name["Gelidus"].get_controlled_by() is None)


async def test_populate_empty_planets():
    data = {
        "node": [{"id": 0, "label": ""},
                 {"id": 1, "label": ""}],
        "edge": [{"source": 0, "target": 1}]
    }
    state = GalacticWarState(data)
    for node in state._data["node"]:
        planet = Planet(node)
        assert(len(planet.get_name()) > 0)
        assert(len(planet.get_map()) > 0)
        assert(len(planet.get_mod()) > 0)
        assert(planet.get_size() > 0)
        assert(planet.get_score(Faction.arm) > 0)
        assert(planet.get_score(Faction.core) > 0)


async def test_assign_capitals():
    data = {
        "node": [{"id": 10, "label": "a"},
                 {"id": 11, "label": "b"},
                 {"id": 12, "label": "c"},
                 {"id": 13, "label": "d"},
                 {"id": 14, "label": "e"},
                 {"id": 15, "label": "f"},
                 {"id": 16, "label": "g"},
                 {"id": 17, "label": "h"},
                 {"id": 18, "label": "i"}],
        "edge": [{"source": 10, "target": 11},  # a path to 18 with 4 edges
                 {"source": 11, "target": 12},
                 {"source": 12, "target": 13},
                 {"source": 13, "target": 18},

                 {"source": 10, "target": 14},  # a path to 18 with 3 edges
                 {"source": 14, "target": 15},
                 {"source": 15, "target": 18},

                 {"source": 10, "target": 16},  # another path to 18 with 3 edges
                 {"source": 16, "target": 17},
                 {"source": 17, "target": 18}]
    }
    state = GalacticWarState(data)

    state.assign_two_capitals()
    state = GalacticWarState(state.get_data())
    assert(len(state.get_uncontested_planets()) == 2)
    assert(len(state.get_capitals()) == 2)


async def test_bugfix1(periodic_update_galactic_war_service):
    # Planet.get_score(Faction) always returned Planet.size
    # because dictionary lookup used faction.name instead of faction
    service = periodic_update_galactic_war_service
    service._state._planets_by_name["Thalassean"].set_controlled_by(Faction.core)
    service._state._planets_by_name["Barathrum"].set_controlled_by(Faction.core)
    service._state._planets_by_name["Lusch"].set_controlled_by(Faction.core)
    service._state._planets_by_name["Gelidus"].set_controlled_by(None)
    service._state._planets_by_name["Gelidus"].set_score(Faction.core, 50.)
    service._state._planets_by_name["Gelidus"].set_score(Faction.arm, 50.)
    service._state._planets_by_name["Dump"].set_controlled_by(None)
    service._state._planets_by_name["Dump"].set_score(Faction.core, 100.822)
    service._state._planets_by_name["Dump"].set_score(Faction.arm, 44.425)
    service._state._planets_by_name["Rougpelt"].set_controlled_by(None)
    service._state._planets_by_name["Rougpelt"].set_score(Faction.core, 50.)
    service._state._planets_by_name["Rougpelt"].set_score(Faction.arm, 50.)

    game_info = EndedGameInfo(
        13733,
        'ladder1v1_tavmod',
        2447, '[Pro] Comet Catcher',
        "tavmod",
        "Dump",
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 0, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 1, Faction.arm, GameOutcome.DEFEAT),
        ],
    )

    old_ratings = {
        1: RankedRating(1744.170, 185.524, 1, 10),
        2: RankedRating(1255.830, 185.524, 2, 10)
    }
    new_ratings = {
        1: Rating(1766.175, 179.436),
        2: Rating(1233.825, 179.436)
    }
    team_outcome_likelihoods = {
        0: OutcomeLikelihoods(0.01, 0., 0.99),
        1: OutcomeLikelihoods(0.99, 0., 0.01),
    }

    await service.on_game_rating(game_info, old_ratings, new_ratings, team_outcome_likelihoods)
    assert(service._state._planets_by_name["Dump"].get_controlled_by() is None)
    assert(service._state._planets_by_name["Dump"].get_score(Faction.core) > 100.822)
    assert(service._state._planets_by_name["Dump"].get_score(Faction.arm) < 44.425)


async def test_distribute_empty_planets(ladder_service):
    data = {
        "node": [{"id": 10, "label": "a", "capital_of": "arm", "controlled_by": "arm"},
                 {"id": 11, "label": "b"},
                 {"id": 12, "label": "c"},
                 {"id": 13, "label": "d"},
                 {"id": 14, "label": "e"},
                 {"id": 15, "label": "f"},
                 {"id": 16, "label": "g"},
                 {"id": 17, "label": "h"},
                 {"id": 18, "label": "i", "capital_of": "core", "controlled_by": "core"}],
        "edge": [{"source": 10, "target": 11},  # a path to 18 with 4 edges
                 {"source": 11, "target": 12},
                 {"source": 12, "target": 13},
                 {"source": 13, "target": 18},

                 {"source": 10, "target": 14},  # a path to 18 with 3 edges
                 {"source": 14, "target": 15},
                 {"source": 15, "target": 18},

                 {"source": 10, "target": 16},  # another path to 18 with 3 edges
                 {"source": 16, "target": 17},
                 {"source": 17, "target": 18}]
    }

    state = GalacticWarState(data)
    assert(len(state.get_uncontested_planets()) == 2)
    state.distribute_planets_to_factions()
    state.seperate_abutting_factions()
    state.ensure_ranked_maps(ladder_service.queues)
    state = GalacticWarState(state.get_data())

    def xor(a, b):
        return (a and (not b)) or ((not a) and b)

    assert(state._planets_by_id[12].get_controlled_by() is None)
    assert(xor(state._planets_by_id[14].get_controlled_by() is None, state._planets_by_id[15].get_controlled_by() is None))
    assert(xor(state._planets_by_id[16].get_controlled_by() is None, state._planets_by_id[17].get_controlled_by() is None))

    assert(state._planets_by_id[11].get_controlled_by() == Faction.arm)
    assert(state._planets_by_id[13].get_controlled_by() == Faction.core)
    assert(state._planets_by_id[13].get_controlled_by() == Faction.core)
    assert(xor(state._planets_by_id[14].get_controlled_by() == Faction.arm, state._planets_by_id[15].get_controlled_by() == Faction.core))
    assert(xor(state._planets_by_id[16].get_controlled_by() == Faction.arm, state._planets_by_id[17].get_controlled_by() == Faction.core))

    for node in data["node"]:
        assert(node["map"] != "SHERWOOD")

