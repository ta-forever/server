from typing import Dict, List, NamedTuple

from trueskill import Rating

from server.games.game_results import GameOutcome
from server.games.typedefs import EndedGamePlayerSummary

PlayerID = int


class TeamRatingData(NamedTuple):
    outcome: GameOutcome
    ratings: Dict[int, Rating]


GameRatingData = List[TeamRatingData]


class GameRatingSummary(NamedTuple):
    """
    Holds minimal information needed to rate a game.
    Fields:
     - game_id: id of the game to rate
     - rating_type: str (e.g. "ladder1v1")
     - teams: a list of two TeamRatingSummaries
    """

    game_id: int
    rating_type: str
    featured_mod: str
    player_data: List[EndedGamePlayerSummary]

    @classmethod
    def from_game_info_dict(cls, game_info: Dict) -> "GameRatingSummary":
        if len(game_info["teams"]) < 2:
            raise ValueError("Detected fewer than two teams.")

        return cls(
            game_info["game_id"],
            game_info["rating_type"],
            game_info["featured_mod"],
            [
                EndedGamePlayerSummary(
                    getattr(GameOutcome, summary["outcome"]), set(summary["player_ids"])
                )
                for summary in game_info["teams"]
            ],
        )


class RatingServiceError(Exception):
    pass


class ServiceNotReadyError(RatingServiceError):
    pass
