from dataclasses import dataclass
from enum import Enum, unique

from typing import List, Dict

from server.factions import Faction


@unique
class GwMapSelectStrategy(Enum):
    REGEX = "REGEX"
    MAP_POOL = "MAP_POOL"


@dataclass
class GwModConfig:
    technical_name: str
    map_select_regexes: List[str]
    map_select_mmq_id: int

    @classmethod
    def from_dict(cls, d) -> "GwModConfig":
        return cls(
            technical_name=d["technical_name"],
            map_select_regexes=d.get("map_select_regexes", []),
            map_select_mmq_id=d.get("map_select_mmq_id", None)
        )


@dataclass
class GwGalaxyConfig:
    technical_name: str
    display_name: str
    state_file: str
    map_select_strategy: GwMapSelectStrategy
    mods: Dict[str, GwModConfig]
    rank_avatar_ids: Dict[Faction, List[int]]
    rank_achievement_ids: Dict[Faction, List[str]]
    # Optional: explicit capital planet names.  If both are set and the named
    # planets are found in the scenario, they take precedence over the
    # greatest-distance search.  Falls back to distance search if either name
    # is absent or not found in the loaded scenario.
    arm_capital: str = None
    core_capital: str = None

    @classmethod
    def from_dict(cls, d: Dict) -> "GwGalaxyConfig":
        return cls(
            technical_name=d["technical_name"],
            display_name=d["display_name"],
            state_file=d["state_file"],
            map_select_strategy=GwMapSelectStrategy(d["map_select_strategy"]),
            mods={c["technical_name"]:GwModConfig.from_dict(c) for c in d["mods"]},
            rank_avatar_ids={Faction.from_string(k): [int(_id) for _id in v] for k, v in d["rank_avatar_ids"].items()},
            rank_achievement_ids={Faction.from_string(k): v for k, v in d["rank_achievement_ids"].items()},
            arm_capital=d.get("arm_capital", None),
            core_capital=d.get("core_capital", None),
        )

    @classmethod
    def from_dict_list(cls, dl: List[Dict]) -> Dict[str, "GwGalaxyConfig"]:
        return {d["technical_name"]:GwGalaxyConfig.from_dict(d) for d in dl}


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
