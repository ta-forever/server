from dataclasses import dataclass

@dataclass
class GwPlayerScore:
    wins: int = 0
    cum_winning_scores: float = 0.0
    losses: int = 0
    cum_losing_scores: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "GwPlayerScore":
        return cls(
            wins=int(data.get("wins", 0)),
            cum_winning_scores=float(data.get("cum_winning_scores", 0.0)),
            losses=int(data.get("losses", 0)),
            cum_losing_scores=float(data.get("cum_losing_scores", 0.0)),
        )
