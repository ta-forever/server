from dataclasses import dataclass

@dataclass
class GwPlayerScore:
    wins: int = 0
    cum_winning_scores: float = 0.0
    losses: int = 0
    cum_losing_scores: float = 0.0
