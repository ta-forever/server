import random
from typing import Dict, Union, List
from server.config import config
from server.decorators import with_logger
from server.factions import Faction
from server.galactic_war.typedefs import GwPlayerScore
from server.rating_service.typedefs import PlayerID

random.seed()

# Each entry is (word, gender) where gender is 'm', 'f', or 'n'
LATIN_NOUNS = []
with open("latin_nouns.txt", "r") as fp:
    for line in fp:
        parts = line.strip().split()
        if len(parts) == 2:
            LATIN_NOUNS.append((parts[0], parts[1]))

# Each entry is (masc_form, fem_form, neut_form)
LATIN_ADJECTIVES = []
with open("latin_adjectives.txt", "r") as fp:
    for line in fp:
        parts = line.strip().split()
        if len(parts) == 3:
            LATIN_ADJECTIVES.append((parts[0], parts[1], parts[2]))


def get_random_noun():
    nouns = LATIN_NOUNS.copy()
    random.shuffle(nouns)
    for noun in nouns:
        yield noun


def get_random_adjective():
    adjs = LATIN_ADJECTIVES.copy()
    random.shuffle(adjs)
    for adj in adjs:
        yield adj


_random_noun_gen = get_random_noun()
_random_adj_gen = get_random_adjective()


def _reset_random_nouns():
    global _random_noun_gen
    _random_noun_gen = get_random_noun()


def _reset_random_adjs():
    global _random_adj_gen
    _random_adj_gen = get_random_adjective()


def get_random_name():
    try:
        noun, gender = next(_random_noun_gen)
    except StopIteration:
        _reset_random_nouns()
        noun, gender = next(_random_noun_gen)

    try:
        adj_m, adj_f, adj_n = next(_random_adj_gen)
    except StopIteration:
        _reset_random_adjs()
        adj_m, adj_f, adj_n = next(_random_adj_gen)

    adj = adj_f if gender == 'f' else adj_n if gender == 'n' else adj_m
    return f"{noun} {adj}"


def is_number(s: str):
    try:
        x = float(s)
        return True
    except ValueError:
        return False


@with_logger
class Planet(object):
    """
    :brief wrapper around a dictionary containing Galactic War planet attributes
    """

    def __init__(self, _data: Dict, default_mod: str):
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
            "map": "<invalid map>",
            "mod": default_mod,
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

    def set_name(self, new_name):
        self._data["label"] = new_name

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
                self._data["belligerents"].clear()
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
        if max_score > config.GALACTIC_WAR_DOMINANCE_THRESHOLD * min_score:
            try:
                return Faction.from_value(max_faction)
            except KeyError:
                return None
        else:
            return None

    def get_belligerents(self) -> List[PlayerID]:
        return [pid for pid in self._data["belligerents"].keys()]

    def get_belligerent_score(self, player_id: PlayerID, faction: Faction) -> GwPlayerScore:
        score = self._data["belligerents"].get(player_id, {}).get(faction.capitalized)
        default_score = GwPlayerScore()

        if score is None:
            self.set_belligerent_score(player_id, faction, default_score)
            return default_score

        if isinstance(score, GwPlayerScore):
            return score

        score = GwPlayerScore(**score)
        self.set_belligerent_score(player_id, faction, score)
        return score

    def set_belligerent_score(self, player_id: PlayerID, faction: Faction, score: GwPlayerScore):
        if player_id not in self._data["belligerents"]:
            self._data["belligerents"][player_id] = {faction.capitalized: score}
        else:
            self._data["belligerents"][player_id][faction.capitalized] = score

    def adjust_belligerent(self, player_id: PlayerID, faction: Faction, score_change: float):
        score = self.get_belligerent_score(player_id, faction)
        if score_change > 0.:
            score.wins += 1
            score.cum_winning_scores += score_change
        elif score_change < 0.:
            score.losses += 1
            score.cum_losing_scores += score_change

    def get_most_heroic_player(self, faction: Faction):
        belligerents = self.get_belligerents()
        if not belligerents:
            return None, None

        heroic_player_id, cum_winning_score = max((
            (pid, self.get_belligerent_score(pid, faction).cum_winning_scores)
            for pid in self.get_belligerents()
        ), key=lambda item: item[1])

        return heroic_player_id, cum_winning_score
