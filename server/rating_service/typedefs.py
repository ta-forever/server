from typing import Dict, List, NamedTuple

from trueskill import Rating

from server.games.game_results import GameOutcome

PlayerID = int
TeamID = int

class TeamRatingData(NamedTuple):
    outcome: GameOutcome
    ratings: Dict[PlayerID, Rating]


GameRatingData = List[TeamRatingData]


class RankedRating(NamedTuple):
    mean: float         # rating
    sigma: float        # rating
    rank: int           # rank in leaderboard [0..leaderboard_size) top to bottom
    leaderboard_size: int

    @property
    def rating(self):
        return Rating(self.mean, self.sigma)

    @property
    def penis_points(self):
        return self.mean - 3. * self.sigma


class RatingServiceError(Exception):
    pass


class ServiceNotReadyError(RatingServiceError):
    pass
