import pytest
from trueskill import Rating

from server.factions import Faction
from server.games.game_results import GameOutcome
from server.games.typedefs import EndedGamePlayerSummary
from server.rating_service.game_rater import GameRater


@pytest.fixture
def rating_data_1v1():
    player1_id = 1
    player1_rating = Rating(1500, 500)
    player1_outcome = GameOutcome.VICTORY

    player2_id = 2
    player2_rating = Rating(1400, 400)
    player2_outcome = GameOutcome.DEFEAT

    return (
        [EndedGamePlayerSummary(player1_id, 1, Faction.arm, player1_outcome),
         EndedGamePlayerSummary(player2_id, 2, Faction.core, player2_outcome)],
        {player1_id: player1_rating,
         player2_id: player2_rating}
    )


@pytest.fixture
def rating_data_2v2():
    player1_id = 1
    player1_rating = Rating(1500, 500)

    player2_id = 2
    player2_rating = Rating(1400, 400)

    player3_id = 3
    player3_rating = Rating(1300, 300)

    player4_id = 4
    player4_rating = Rating(1200, 200)

    team1_outcome = GameOutcome.VICTORY
    team2_outcome = GameOutcome.DEFEAT

    return (
        [EndedGamePlayerSummary(player1_id, 1, Faction.arm, team1_outcome),
         EndedGamePlayerSummary(player2_id, 1, Faction.arm, team1_outcome),
         EndedGamePlayerSummary(player3_id, 2, Faction.core, team2_outcome),
         EndedGamePlayerSummary(player4_id, 2, Faction.core, team2_outcome)],
        {player1_id: player1_rating,
         player2_id: player2_rating,
         player3_id: player3_rating,
         player4_id: player4_rating}
    )


def test_compute_rating_1v1(rating_data_1v1):
    player_game_info, old_ratings = rating_data_1v1
    new_ratings, likelihood_outcomes = GameRater.compute_rating(player_game_info, old_ratings)

    assert new_ratings[1] > old_ratings[1]
    assert new_ratings[2] < old_ratings[2]

    assert new_ratings[1].sigma < old_ratings[1].sigma
    assert new_ratings[2].sigma < old_ratings[2].sigma

    assert likelihood_outcomes[1].pwin > likelihood_outcomes[2].pwin
    assert likelihood_outcomes[1].pwin + likelihood_outcomes[1].pdraw + likelihood_outcomes[1].plose > 0.999
    assert likelihood_outcomes[1].pwin + likelihood_outcomes[1].pdraw + likelihood_outcomes[1].plose < 1.001


def test_compute_rating_2v2(rating_data_2v2):
    player_game_info, old_ratings = rating_data_2v2
    new_ratings, likelihood_outcomes = GameRater.compute_rating(player_game_info, old_ratings)

    assert new_ratings[1] > old_ratings[1]
    assert new_ratings[2] > old_ratings[2]
    assert new_ratings[3] < old_ratings[3]
    assert new_ratings[4] < old_ratings[4]

    assert new_ratings[1].sigma < old_ratings[1].sigma
    assert new_ratings[2].sigma < old_ratings[2].sigma
    assert new_ratings[3].sigma < old_ratings[3].sigma
    assert new_ratings[4].sigma < old_ratings[4].sigma

    assert likelihood_outcomes[1].pwin > likelihood_outcomes[2].pwin
