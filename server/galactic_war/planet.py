import random
from typing import Dict, Union, List
from server.config import config
from server.factions import Faction
from server.rating_service.typedefs import PlayerID

random.seed()

LATIN_NOUNS = []
with open("latin_nouns.txt", "r") as fp:
    for line in fp:
        LATIN_NOUNS += [line.strip().capitalize()]
    LATIN_NOUNS = random.sample(LATIN_NOUNS, len(LATIN_NOUNS))


LATIN_ADJECTIVES = []
with open("latin_adjectives.txt", "r") as fp:
    for line in fp:
        LATIN_ADJECTIVES += [line.strip().capitalize()]
    LATIN_ADJECTIVES = random.sample(LATIN_ADJECTIVES, len(LATIN_ADJECTIVES))


def get_random_noun():
    idx = 0
    while True:
        yield LATIN_NOUNS[idx % len(LATIN_NOUNS)]
        idx += 1


def get_random_adjective():
    idx = 0
    while True:
        yield LATIN_ADJECTIVES[idx % len(LATIN_ADJECTIVES)]
        idx += 1


def get_random_name():
    return get_random_noun()


def get_random_mod():
    mod_list = [mod.split(':') for mod in config.GALACTIC_WAR_INITIALISE_DEFAULT_MOD.split(';')]
    mod_list = [[m[0], int(m[1])] for m in mod_list]
    for n in range(1, len(mod_list)):
        mod_list[n][1] += mod_list[n-1][1]
    x = random.randint(0, mod_list[-1][1]-1)
    for mod, threshold in mod_list:
        if x <= threshold:
            return mod


def is_number(s: str):
    try:
        x = float(s)
        return True
    except ValueError:
        return False


class Planet(object):
    """
    :brief wrapper around a dictionary containing Galactic War planet attributes
    """

    def __init__(self, _data: Dict):
        try:
            if len(_data["label"]) == 0:
                _data.pop("label")
        except KeyError as e:
            pass

        try:
            int(_data["label"])
            _data.pop("label")  # purely numeric name.  we should rename it
        except (ValueError, KeyError):
            pass

        default_data = {
            "label": get_random_name(),
            "map": "SHERWOOD",
            "mod": get_random_mod(),
            "size": config.GALACTIC_WAR_DEFAULT_PLANET_SIZE,
            "score": {
                Faction.arm.capitalized: config.GALACTIC_WAR_DEFAULT_PLANET_SIZE,
                Faction.core.capitalized: config.GALACTIC_WAR_DEFAULT_PLANET_SIZE
            },
            "belligerents": {}
        }

        for k, v in default_data.items():
            if k not in _data:
                _data[k] = v

        _data["belligerents"] = {
            int(pid_string): scores
            for pid_string, scores in _data["belligerents"].items()
            if is_number(pid_string)
        }

        self._data = _data

    def get_id(self) -> int:
        return self._data["id"]

    def get_name(self) -> str:
        return self._data["label"]

    def get_map(self) -> str:
        return self._data["map"]

    def set_map(self, map_name: str):
        self._data["map"] = map_name

    def get_mod(self) -> str:
        return self._data["mod"]

    def set_mod(self, mod: str):
        self._data["mod"] = mod

    def get_size(self) -> int:
        return self._data["size"]

    def get_capital_of(self) -> Union[Faction, None]:
        try:
            return Faction.from_value(self._data["capital_of"])
        except KeyError:
            return None

    def set_capital_of(self, faction: Faction):
        if faction is not None:
            self._data["capital_of"] = faction.capitalized
        else:
            try:
                self._data.pop("capital_of")
            except KeyError:
                pass

    def get_controlled_by(self) -> Union[Faction, None]:
        try:
            return Faction.from_value(self._data["controlled_by"])
        except KeyError:
            return None

    def set_controlled_by(self, faction: Union[Faction, None]):
        if faction is None:
            if "controlled_by" in self._data:
                self._data.pop("controlled_by")
        else:
            self._data["controlled_by"] = faction.capitalized

    def get_score(self, faction: Faction) -> float:
        try:
            return float(self.get_ro_scores()[faction])
        except KeyError:
            return self.get_size()

    def get_ro_scores(self) -> Dict[Faction, float]:
        return {
            Faction.from_value(faction_name): float(score)
            for faction_name, score in self._data["score"].items()
            if faction_name.lower() in Faction.__members__
        }

    def set_score(self, faction: Faction, value: float):
        self._data["score"][faction.capitalized] = value

    def reset_scores(self):
        for f in self.get_ro_scores().keys():
            self.set_score(f, self.get_size())

    def get_dominant_faction(self) -> Union[Faction, None]:
        scores = self.get_ro_scores()
        min_score = min(scores.values())
        max_faction = max(scores, key=scores.get)
        max_score = scores[max_faction]
        if max_score > config.GALACTIC_WAR_REQUIRED_DOMINANCE_RATIO * min_score:
            try:
                return Faction.from_value(max_faction)
            except KeyError:
                return None
        else:
            return None

    def get_belligerents(self) -> List[PlayerID]:
        return [pid for pid in self._data["belligerents"].keys()]

    def get_belligerent_score(self, player_id: PlayerID, faction: Faction) -> float:
        return self._data["belligerents"].get(player_id, {}).get(faction.capitalized, 0.0)

    def set_belligerent_score(self, player_id: PlayerID, faction: Faction, score: float):
        if player_id not in self._data["belligerents"]:
            self._data["belligerents"][player_id] = {faction.capitalized: score}
        else:
            self._data["belligerents"][player_id][faction.capitalized] = score

    def adjust_belligerent(self, player_id: PlayerID, faction: Faction, score_change: float):
        score = self.get_belligerent_score(player_id, faction)
        self.set_belligerent_score(player_id, faction, score + score_change)
