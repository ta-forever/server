from typing import Dict, List

import trueskill
from trueskill import Rating

from server.games.game_results import GameOutcome

from ..decorators import with_logger
from .typedefs import GameRatingData, PlayerID


class GameRatingError(Exception):
    pass


@with_logger
class GameRater:
    @classmethod
    def compute_rating(cls, rating_data: GameRatingData) -> Dict[PlayerID, Rating]:
        rating_groups = [team.ratings for team in rating_data]
        team_outcomes = [team.outcome for team in rating_data]
        if len(team_outcomes) == 2:
            ranks = cls._ranks_from_two_team_outcomes(team_outcomes)
        else:
            raise GameRatingError("Sorry multiteam/ffa not implemented")

        cls._logger.debug("Rating groups: %s", rating_groups)
        cls._logger.debug("Ranks: %s", ranks)

        new_rating_groups = trueskill.rate(rating_groups, ranks)

        player_rating_map = {
            player_id: new_rating
            for team in new_rating_groups
            for player_id, new_rating in team.items()
        }

        player_rating_map = {
            player_id: (team.outcome, old_rating, player_rating_map[player_id])
            for team in rating_data
            for player_id, old_rating in team.ratings.items()
        }

        def penis_points(rating: Rating):
            return rating.mu - 3. * rating.sigma

        cls._logger.info("rating changes: %s", player_rating_map)

        player_rating_map = {
            player_id: old_rating if outcome == GameOutcome.VICTORY and
                                     penis_points(new_rating) < penis_points(old_rating) else new_rating
            for player_id, (outcome, old_rating, new_rating) in player_rating_map.items()
        }

        cls._logger.info("settled ratings: %s", player_rating_map)
        return player_rating_map

    @staticmethod
    def _ranks_from_two_team_outcomes(outcomes: List[GameOutcome]) -> List[int]:
        if outcomes == [GameOutcome.DRAW, GameOutcome.DRAW]:
            return [0, 0]
        elif outcomes == [GameOutcome.VICTORY, GameOutcome.DEFEAT]:
            return [0, 1]
        elif outcomes == [GameOutcome.DEFEAT, GameOutcome.VICTORY]:
            return [1, 0]
        else:
            raise GameRatingError(f"Inconsistent outcomes {outcomes}")
