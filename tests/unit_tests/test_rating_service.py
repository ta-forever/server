from unittest import mock

import pytest
from asynctest import CoroutineMock
from sqlalchemy import and_, select
from trueskill import Rating

from server.db import FAFDatabase
from server.db.models import (
    game_player_stats,
    leaderboard_rating,
    leaderboard_rating_journal
)
from server.factions import Faction
from server.games.game_results import GameOutcome
from server.games.typedefs import (
    EndedGameInfo,
    ValidityState, EndedGamePlayerSummary, FeaturedModType
)
from server.rating import RatingType
from server.rating_service.rating_service import (
    RatingService,
    ServiceNotReadyError
)
from server.rating_service.typedefs import RankedRating

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def rating_service(database, player_service):
    service = RatingService(database, player_service)
    await service.initialize()
    yield service
    service.kill()


@pytest.fixture
def uninitialized_service(database, player_service):
    return RatingService(database, player_service)


@pytest.fixture
async def semiinitialized_service(database, player_service):
    service = RatingService(database, player_service)
    await service.update_data()
    return service


@pytest.fixture
def game_info():
    return EndedGameInfo(
        1,
        RatingType.GLOBAL,
        1, "SHERWOOD",
        FeaturedModType.DEFAULT,
        None,
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 2, Faction.arm, GameOutcome.DEFEAT),
        ],
    )

@pytest.fixture
def game_info_2v2():
    return EndedGameInfo(
        1,
        RatingType.GLOBAL,
        1, "SHERWOOD",
        FeaturedModType.DEFAULT,
        None,
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 1, Faction.arm, GameOutcome.VICTORY),
            EndedGamePlayerSummary(3, 2, Faction.core, GameOutcome.DEFEAT),
            EndedGamePlayerSummary(4, 2, Faction.arm, GameOutcome.DEFEAT),
        ],
    )


@pytest.fixture
def bad_game_info():
    """
    Should throw a GameRatingError.
    """
    return EndedGameInfo(
        1,
        RatingType.GLOBAL,
        1, "SHERWOOD",
        FeaturedModType.DEFAULT,
        None,
        [],
        {},
        ValidityState.VALID,
        [
            EndedGamePlayerSummary(1, 1, Faction.core, GameOutcome.VICTORY),
            EndedGamePlayerSummary(2, 2, Faction.arm, GameOutcome.VICTORY),
        ],
    )


async def test_enqueue_manual_initialization(uninitialized_service, game_info):
    service = uninitialized_service
    await service.initialize()
    service._rate = CoroutineMock()
    await service.enqueue(game_info)
    await service.shutdown()

    service._rate.assert_called()


async def double_initialization_does_not_start_second_worker(rating_service):
    worker_task_id = id(rating_service._task)

    await rating_service.initialize()

    assert worker_task_id == id(rating_service._task)


async def test_enqueue_initialized(rating_service, game_info):
    service = rating_service
    service._rate = CoroutineMock()

    await service.enqueue(game_info)
    await service.shutdown()

    service._rate.assert_called()


async def test_enqueue_uninitialized(uninitialized_service, game_info):
    service = uninitialized_service
    with pytest.raises(ServiceNotReadyError):
        await service.enqueue(game_info)
    await service.shutdown()


async def test_get_rating_uninitialized(uninitialized_service):
    service = uninitialized_service
    with pytest.raises(ServiceNotReadyError):
        await service._get_player_ratings({1}, RatingType.GLOBAL)


async def test_load_rating_type_ids(uninitialized_service):
    service = uninitialized_service
    await service.update_data()

    assert service._rating_type_ids == {
        "global": 1,
        "ladder1v1": 2,
        "ladder1v1_tavmod": 3
    }


async def test_get_player_rating_global(semiinitialized_service):
    service = semiinitialized_service
    player_id = 50
    true_rating = RankedRating(1200, 250, 3, 7)
    rating = await service._get_player_ratings({player_id}, RatingType.GLOBAL)
    assert rating[50] == true_rating


async def test_get_player_rating_ladder(semiinitialized_service):
    service = semiinitialized_service
    player_id = 50
    true_rating = RankedRating(1300, 400, 3, 7)
    rating = await service._get_player_ratings({player_id}, RatingType.TEST_LADDER)
    assert rating[50] == true_rating


async def get_all_ratings(db: FAFDatabase, player_id: int):
    rating_sql = select([leaderboard_rating]).where(
        and_(leaderboard_rating.c.login_id == player_id)
    )

    async with db.acquire() as conn:
        result = await conn.execute(rating_sql)
        rows = await result.fetchall()

    return rows


async def test_get_new_player_rating_created(semiinitialized_service):
    """
    Upon rating games of players without a rating entry in both new and legacy
    tables, a new rating entry should be created.
    """
    service = semiinitialized_service
    player_id = 300
    rating_type = RatingType.TEST_LADDER

    db_ratings = await get_all_ratings(service._db, player_id)
    assert len(db_ratings) == 0  # Rating does not exist yet

    await service._get_player_ratings({player_id}, rating_type)

    db_ratings = await get_all_ratings(service._db, player_id)
    assert len(db_ratings) == 1  # Rating has been created
    assert db_ratings[0]["mean"] == 1500
    assert db_ratings[0]["deviation"] == 500


async def test_get_rating_data(semiinitialized_service):
    service = semiinitialized_service
    game_id = 1

    player1_id = 1
    player1_db_rating = RankedRating(2000, 125, 0, 7)
    player1_outcome = GameOutcome.VICTORY

    player2_id = 2
    player2_db_rating = RankedRating(1500, 75, 2, 7)
    player2_outcome = GameOutcome.DEFEAT

    summary = EndedGameInfo(
        game_id,
        RatingType.GLOBAL,
        1, "SHERWOOD", FeaturedModType.DEFAULT, None, [], {}, ValidityState.VALID,
        [
            EndedGamePlayerSummary(player1_id, 1, Faction.core, player1_outcome),
            EndedGamePlayerSummary(player2_id, 2, Faction.arm, player2_outcome),
        ],
    )

    rating_data = await service._get_player_ratings({player1_id, player2_id}, summary.rating_type)
    assert rating_data[player1_id] == player1_db_rating
    assert rating_data[player2_id] == player2_db_rating


async def test_rating(semiinitialized_service, game_info):
    service = semiinitialized_service
    service._persist_rating_changes = CoroutineMock()
    await service._rate(game_info)
    service._persist_rating_changes.assert_called()


async def test_rating_persistence(semiinitialized_service, game_info):
    # Assumes that game_player_stats has an entry for player 1 in game 1.
    service = semiinitialized_service
    game_id = 1
    player_id = 1
    rating_type_id = service._rating_type_ids[RatingType.GLOBAL]
    old_ratings = {player_id: Rating(1000, 500), 2: Rating(1000, 500)}
    after_mean = 1234
    new_ratings = {player_id: Rating(after_mean, 400), 2: Rating(after_mean, 400)}
    await service._persist_rating_changes(game_info, old_ratings, new_ratings)

    async with service._db.acquire() as conn:
        sql = select([game_player_stats.c.id, game_player_stats.c.after_mean]).where(
            and_(
                game_player_stats.c.gameId == game_id,
                game_player_stats.c.playerId == player_id,
            )
        )
        results = await conn.execute(sql)
        gps_row = await results.fetchone()

        sql = select([leaderboard_rating.c.mean]).where(
            and_(
                leaderboard_rating.c.login_id == player_id,
                leaderboard_rating.c.leaderboard_id == rating_type_id,
            )
        )
        results = await conn.execute(sql)
        rating_row = await results.fetchone()

        sql = select([leaderboard_rating_journal.c.rating_mean_after]).where(
            leaderboard_rating_journal.c.game_player_stats_id
            == gps_row[game_player_stats.c.id]
        )
        results = await conn.execute(sql)
        journal_row = await results.fetchone()

    assert gps_row[game_player_stats.c.after_mean] == after_mean
    assert rating_row[leaderboard_rating.c.mean] == after_mean
    assert journal_row[leaderboard_rating_journal.c.rating_mean_after] == after_mean


async def test_update_player_service(uninitialized_service, player_service):
    service = uninitialized_service
    player_id = 1
    player_service._players = {player_id: mock.MagicMock()}

    service._on_player_rating_change(player_id, RatingType.GLOBAL, Rating(1000, 100))

    player_service[player_id].ratings.__setitem__.assert_called()


async def test_game_rating_error_handled(rating_service, game_info, bad_game_info):
    service = rating_service
    service._persist_rating_changes = CoroutineMock()
    service._logger = mock.Mock()

    await service.enqueue(bad_game_info)
    await service.enqueue(game_info)

    await service._join_rating_queue()

    # first game: error has been logged.
    service._logger.warning.assert_called()
    # second game: results have been saved.
    service._persist_rating_changes.assert_called_once()


async def test_game_update_empty_resultset(rating_service):
    service = rating_service
    game_id = 2
    player_id = 1
    rating_type = RatingType.GLOBAL
    old_ratings = {player_id: Rating(1000, 500)}
    after_mean = 1234
    new_ratings = {player_id: Rating(after_mean, 400)}

    game_info = EndedGameInfo(
        game_id, rating_type, 0, "SHERWOOD", FeaturedModType.DEFAULT, None, [], {}, ValidityState.VALID,
        [EndedGamePlayerSummary(player_id, 0, Faction.core, GameOutcome.VICTORY),
         EndedGamePlayerSummary(player_id, 0, Faction.core, GameOutcome.DEFEAT)])

    await service._persist_rating_changes(
        game_info, old_ratings, new_ratings
    )

async def test_game_rating_callbacks(rating_service, game_info):
    service = rating_service
    service._get_player_ratings = CoroutineMock(return_value={
        1: RankedRating(1234., 123., 1, 10),
        2: RankedRating(1212., 50., 2, 10)
    })

    class Consumer(object):
        def __init__(self):
            self.rating_results = None

        async def set_rating_results(self, game_info, old_ratings, new_ratings, likelihoods):
            self.rating_results = [game_info, old_ratings, new_ratings, likelihoods]

        def get_rating_results(self):
            return self.rating_results

    consumer = Consumer()
    service.add_game_rating_callback(lambda gi, old, new, likelihoods: consumer.set_rating_results(gi, old, new, likelihoods))

    await service.enqueue(game_info)
    await service._join_rating_queue()

    assert (consumer.get_rating_results() is not None)
    gi, old_ratings, new_ratings, likelihoods = consumer.get_rating_results()
    assert (gi == game_info)
    assert (old_ratings[1] == RankedRating(1234., 123., 1, 10))
    assert (old_ratings[2] == RankedRating(1212., 50., 2, 10))
    assert (new_ratings[1].mu > 1234.)
    assert (new_ratings[1].sigma < 124.)
    assert (new_ratings[2].mu < 1212.)
    assert (new_ratings[2].sigma < 51.)


async def test_game_rating_2v2(rating_service, game_info_2v2):
    service = rating_service
    service._get_player_ratings = CoroutineMock(return_value={
        1: RankedRating(1000., 100., 1, 10),
        2: RankedRating(1100., 100., 2, 10),
        3: RankedRating(900., 100., 3, 10),
        4: RankedRating(1200., 100., 4, 10)
    })

    class Consumer(object):
        def __init__(self):
            self.rating_results = None

        def set_rating_results(self, game_info, old_ratings, new_ratings, likelihoods):
            self.rating_results = [game_info, old_ratings, new_ratings, likelihoods]

        def get_rating_results(self):
            return self.rating_results

    consumer = Consumer()
    service.add_game_rating_callback(lambda gi, old, new, likelihoods: consumer.set_rating_results(gi, old, new, likelihoods))

    await service.enqueue(game_info_2v2)
    await service._join_rating_queue()

    assert (consumer.get_rating_results() is not None)
    gi, old_ratings, new_ratings, likelihoods = consumer.get_rating_results()
    assert (new_ratings[1].mu > 1000.)
    assert (new_ratings[2].mu > 1100.)
    assert (new_ratings[3].mu < 900.)
    assert (new_ratings[4].mu < 1200.)
