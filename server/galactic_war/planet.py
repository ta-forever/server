from typing import Dict, Union
from server.config import config


class Planet(object):
    """
    :brief light weight wrapper around a dictionary containing Galactic War planet attributes
    """

    def __init__(self, data: Dict):
        self._data = data

    def get_id(self) -> int:
        return self._data["id"]

    def get_name(self) -> str:
        return self._data["label"]

    def get_map(self) -> str:
        return self._data["map"]

    def get_mod(self) -> str:
        return self._data["mod"]

    def get_size(self) -> int:
        return self._data["size"]

    def get_capital_of(self) -> Union[str, None]:
        try:
            return self._data["capital_of"].lower()
        except KeyError:
            return None

    def get_controlled_by(self) -> Union[str, None]:
        try:
            return self._data["controlled_by"].lower()
        except KeyError:
            return None

    def set_controlled_by(self, faction: Union[str, None]):
        if faction is None:
            if "controlled_by" in self._data:
                self._data.pop("controlled_by")
        else:
            self._data["controlled_by"] = faction.lower()

    def get_score(self, faction: str) -> float:
        try:
            return float(self.get_ro_scores()[faction.lower()])
        except KeyError:
            return self.get_size()

    def get_ro_scores(self) -> Dict[str, float]:
        return {faction.lower(): float(score) for faction, score in self._data["score"].items()}

    def set_score(self, faction: str, value: float):
        self._data["score"][faction.lower()] = value

    def reset_scores(self):
        for f in self.get_ro_scores().keys():
            self.set_score(f, self.get_size())

    def get_dominant_faction(self) -> Union[str, None]:
        scores = self.get_ro_scores()
        min_score = min(scores.values())
        max_faction = max(scores, key=scores.get)
        max_score = scores[max_faction]
        if max_score > config.GALACTIC_WAR_REQUIRED_DOMINANCE_RATIO * min_score:
            return max_faction
        else:
            return None
