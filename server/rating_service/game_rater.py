from typing import Dict, List, Tuple
import math
import scipy.stats
import trueskill
from trueskill import Rating

from server.games.game_results import GameOutcome

from ..decorators import with_logger
from .typedefs import PlayerID, TeamID
from ..games.typedefs import EndedGamePlayerSummary, OutcomeLikelihoods


class GameRatingError(Exception):
    pass


@with_logger
class GameRater:
    @classmethod
    def compute_rating(cls,
                       player_data: List[EndedGamePlayerSummary],
                       ratings: Dict[PlayerID, Rating]) -> Tuple[Dict[PlayerID, Rating], Dict[TeamID, OutcomeLikelihoods]]:

        rating_groups = {team_id:{pd.player_id: ratings[pd.player_id] for pd in player_data if pd.team_id == team_id}
                         for team_id in dict.fromkeys([pd.team_id for pd in player_data])}
        team_outcomes = {team_id:list(set([pd.outcome for pd in player_data if pd.team_id == team_id]))
                         for team_id in dict.fromkeys([pd.team_id for pd in player_data])}

        for team_id, to in team_outcomes.items():
            if len(to) != 1:
                raise GameRatingError("Players/teams have inconsistent team outcomes! player_data={}".format(
                                 str([pd.to_dict() for pd in player_data])))

        team_outcomes = {team_id:to[0] for team_id, to in team_outcomes.items()}

        if len(team_outcomes) == 2:
            ranks = cls._ranks_from_two_team_outcomes(list(team_outcomes.values()))
        else:
            raise GameRatingError("Sorry multiteam/ffa not implemented")

        cls._logger.debug("Rating groups: %s", rating_groups)
        cls._logger.debug("Ranks: %s", ranks)

        new_rating_groups: List[Dict[PlayerID, Rating]] = trueskill.rate(list(rating_groups.values()), ranks)
        cls._logger.debug("New Rating groups: %s", new_rating_groups)

        new_ratings = {
            player_id: new_rating
            for team in new_rating_groups
            for player_id, new_rating in team.items()
        }
        cls._logger.debug("New Ratings (canonical): %s", new_rating_groups)

        def penis_points(rating: Rating):
            return rating.mu - 3. * rating.sigma

        new_ratings = {
            pd.player_id: ratings[pd.player_id]
            if pd.outcome == GameOutcome.DRAW or
               pd.outcome == GameOutcome.VICTORY and penis_points(new_ratings[pd.player_id]) < penis_points(ratings[pd.player_id])
            else new_ratings[pd.player_id]
            for pd in player_data
        }

        agg_original_team_ratings = {
            team_id: GameRater.aggregate_team_rating([rating for player_id, rating in rating_group.items()])
            for team_id, rating_group in rating_groups.items()
        }

        def other_team_id(id1):
            return [id2 for id2 in agg_original_team_ratings.keys() if id2 != id1][0]

        team_outcome_likelihoods = {
            team_id: OutcomeLikelihoods(
                GameRater.likelihood_win_1v1(agg_team_rating, agg_original_team_ratings[other_team_id(team_id)]),
                GameRater.likelihood_draw_1v1(agg_team_rating, agg_original_team_ratings[other_team_id(team_id)]),
                GameRater.likelihood_lose_1v1(agg_team_rating, agg_original_team_ratings[other_team_id(team_id)]))
            for team_id, agg_team_rating in agg_original_team_ratings.items()
        }

        cls._logger.info("settled ratings:%s, likelihood:%s", new_ratings, team_outcome_likelihoods)
        return new_ratings, team_outcome_likelihoods

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

    @staticmethod
    def aggregate_team_rating(team_ratings: List[Rating]) -> Rating:
        if len(team_ratings) == 0:
            return Rating(None, None)
        mu = sum([r.mu for r in team_ratings]) / len(team_ratings)
        sigma = math.sqrt(sum([r.sigma*r.sigma for r in team_ratings]) / len(team_ratings))
        return Rating(mu, sigma)

    @staticmethod
    def likelihood(r1: Rating, outcome1: GameOutcome, r2: Rating, outcome2,
                   env: trueskill.TrueSkill = trueskill.global_env()) -> float:
        if outcome1 == outcome2:
            return GameRater.likelihood_draw_1v1(r1, r2, env)
        elif outcome1 == GameOutcome.VICTORY:
            return GameRater.likelihood_win_1v1(r1, r2, env)
        else:
            return GameRater.likelihood_lose_1v1(r1, r2, env)

    @staticmethod
    def likelihood_draw_1v1(r1: Rating, r2: Rating, env: trueskill.TrueSkill = trueskill.global_env()) -> float:
        eps = GameRater.draw_margin(env)
        mu = r1.mu - r2.mu
        sigma = math.sqrt(r1.sigma*r1.sigma + r2.sigma*r2.sigma + 2.0*env.beta*env.beta)
        return scipy.stats.norm.cdf((eps-mu)/sigma) - scipy.stats.norm.cdf((-eps-mu)/sigma)

    @staticmethod
    def likelihood_win_1v1(r1: Rating, r2: Rating, env: trueskill.TrueSkill = trueskill.global_env()) -> float:
        eps = GameRater.draw_margin(env)
        mu = r1.mu - r2.mu
        sigma = math.sqrt(r1.sigma*r1.sigma + r2.sigma*r2.sigma + 2.0*env.beta*env.beta)
        return 1.0 - scipy.stats.norm.cdf((eps-mu)/sigma)

    @staticmethod
    def likelihood_lose_1v1(r1: Rating, r2: Rating, env: trueskill.TrueSkill = trueskill.global_env()) -> float:
        eps = GameRater.draw_margin(env)
        mu = r1.mu - r2.mu
        sigma = math.sqrt(r1.sigma*r1.sigma + r2.sigma*r2.sigma + 2.0*env.beta*env.beta)
        return scipy.stats.norm.cdf((-eps-mu)/sigma)

    @staticmethod
    def draw_margin(env: trueskill.TrueSkill = trueskill.global_env()) -> float:
        return scipy.stats.norm.ppf(0.5*(env.draw_probability+1.0)) * math.sqrt(2.0) * env.beta
