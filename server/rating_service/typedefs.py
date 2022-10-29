from typing import Dict, List, NamedTuple

from trueskill import Rating

from server.games.game_results import GameOutcome
from server.games.typedefs import EndedGamePlayerSummary

PlayerID = int
TeamID = int

class TeamRatingData(NamedTuple):
    outcome: GameOutcome
    ratings: Dict[PlayerID, Rating]


GameRatingData = List[TeamRatingData]


class RatingServiceError(Exception):
    pass


class ServiceNotReadyError(RatingServiceError):
    pass
