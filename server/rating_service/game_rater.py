from typing import Dict, List

import trueskill
from trueskill import Rating

from server.games.game_results import GameOutcome

from ..decorators import with_logger
from .typedefs import PlayerID
from ..games.typedefs import EndedGamePlayerSummary


class GameRatingError(Exception):
    pass


@with_logger
class GameRater:
    @classmethod
    def compute_rating(cls,
                       player_data: List[EndedGamePlayerSummary],
                       ratings: Dict[PlayerID, Rating]) -> Dict[PlayerID, Rating]:

        rating_groups = [{pd.player_id: ratings[pd.player_id] for pd in player_data if pd.team_id == team_id}
                         for team_id in set([pd.team_id for pd in player_data])]
        team_outcomes = [list(set([pd.outcome for pd in player_data if pd.team_id == team_id]))
                         for team_id in set([pd.team_id for pd in player_data])]
        for to in team_outcomes:
            if len(to) != 1:
                raise ValueError("Players/teams have inconsistent team outcomes! player_data={}".format(
                                 str([pd.to_dict() for pd in player_data])))

        team_outcomes = [to[0] for to in team_outcomes]

        if len(team_outcomes) == 2:
            ranks = cls._ranks_from_two_team_outcomes(team_outcomes)
        else:
            raise GameRatingError("Sorry multiteam/ffa not implemented")

        cls._logger.debug("Rating groups: %s", rating_groups)
        cls._logger.debug("Ranks: %s", ranks)

        new_rating_groups: List[Dict[PlayerID, Rating]] = trueskill.rate(rating_groups, ranks)
        cls._logger.debug("New Rating groups: %s", new_rating_groups)

        new_ratings = {
            player_id: new_rating
            for team in new_rating_groups
            for player_id, new_rating in team.items()
        }
        cls._logger.debug("New Ratings: %s", new_rating_groups)

        def penis_points(rating: Rating):
            return rating.mu - 3. * rating.sigma

        new_ratings = {
            pd.player_id: ratings[pd.player_id]
            if pd.outcome == GameOutcome.VICTORY and penis_points(new_ratings[pd.player_id]) < penis_points(ratings[pd.player_id])
            else new_ratings[pd.player_id]
            for pd in player_data
        }

        cls._logger.info("settled ratings: %s", new_ratings)
        return new_ratings

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
