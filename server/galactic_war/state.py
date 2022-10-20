from trueskill import Rating

from .planet import Planet
from collections import defaultdict
import networkx
from typing import List, Tuple, Dict

from ..games.typedefs import EndedGameInfo
from ..rating_service.typedefs import PlayerID


class InvalidGalacticWarGame(Exception):
    """ raised by validate_game when illegal game settings are found """

class State(object):

    def __init__(self, data):
        self._data = data
        self._planets_by_id = {p.get_id(): p for p in [Planet(v) for v in data["node"]]}
        self._planets_by_name = {p.get_name(): p for p in [Planet(v) for v in data["node"]]}
        self._jump_gates = [(edge["source"], edge["target"]) for edge in data["edge"]]
        self._capitals_by_faction = {planet.get_capital_of(): planet
                                     for planet in self._planets_by_id.values()
                                     if planet.get_capital_of() is not None}

        self._neighbours_by_name = {planet_label: [] for planet_label in self._planets_by_name.keys()}
        for edge in data["edge"]:
            source_planet = self._planets_by_id[edge["source"]]
            target_planet = self._planets_by_id[edge["target"]]
            self._neighbours_by_name[source_planet.get_name()] += [target_planet]

    def get_data(self):
        return self._data

    def get_label(self):
        return self._data["label"]

    def validate_game(self, game_info: EndedGameInfo):
        try:
            planet = self.state._planets_by_name[game_info.galactic_war_planet_name]
        except KeyError:
            raise InvalidGalacticWarGame(f"'{game_info.galactic_war_planet_name}' is not part of the current Galactic War scenario")

        if planet.get_map() != game_info.map_name:
            InvalidGalacticWarGame(f"'{planet.get_name()}' should be played on map '{planet.get_map()}', not '{game_info.map_name}'")

        if planet.get_mod() != game_info.game_mode:
            InvalidGalacticWarGame(f"'{planet.get_name()}' should be played with mod '{planet.get_mod()}', not '{game_info.game_mode}'")

        factions_by_team = defaultdict(list)
        for player_info in game_info.endedGamePlayerSummary:
            factions_by_team[player_info.team_id] += [player_info.faction]
            if factions_by_team[player_info.team_id][0] != player_info.faction:
                InvalidGalacticWarGame(f"Galactic War should be played one faction versus another")

        if len(factions_by_team) != 2:
            InvalidGalacticWarGame("Galactic War should be played with exactly two teams")

        team_factions = [factions[0] for factions in factions_by_team.values()]
        if team_factions[0] == team_factions[1]:
            InvalidGalacticWarGame("Galactic War should be played with opposing factions")

        neighbouring_planet_factions = [p.get_controlled_by() for p in self._neighbours_by_name[planet.get_name()]]
        for faction in team_factions:
            if faction not in neighbouring_planet_factions:
                raise InvalidGalacticWarGame(f"{faction} does not have connectivity to planet '{planet.get_name()}'")

        return

    def update_scores(self,
                      game_info: EndedGameInfo,
                      old_ratings: Dict[PlayerID, Rating],
                      new_ratings: Dict[PlayerID, Rating]):
        planet = self._planets_by_name[game_info.galactic_war_planet_name]

        # naive update of dominance
        for player_info in game_info.endedGamePlayerSummary:
            old_rating = old_ratings[player_info.player_id]
            new_rating = new_ratings[player_info.player_id]
            penis_points_change = new_rating.mu - old_rating.mu - 3.*(new_rating.sigma - old_rating.sigma)
            new_planet_score = planet.get_score(player_info.faction.name) + penis_points_change
            planet.set_score(player_info.faction.name, new_planet_score)

        # make sure planet scores never go negative
        scores_by_faction = planet.get_ro_scores()
        min_score = min(scores_by_faction.values())
        if min_score < 0.:
            for faction, dominance in scores_by_faction.items():
                planet.set_score(faction, dominance - min_score)

    def update_front_lines(self, planet=None):
        if planet is None:
            # do planets with higher scores first so if theres a conflict, the higher-scored planet gets precedence
            contested_planets = [p for pid, p in self._planets_by_id.items() if p.get_controlled_by() is None]
            contested_planets.sort(key=lambda p: max(p.get_ro_scores().values()), reverse=True)
            for planet in contested_planets:
                self.update_front_lines(planet)

        else:
            dominant_faction = planet.get_dominant_faction()
            if dominant_faction is not None:
                planet.set_controlled_by(dominant_faction)
                for p in self._neighbours_by_name[planet.get_name()]:
                    f = p.get_dominant_faction()
                    c = p.controlled_by()
                    if (f and f != dominant_faction) or (c and c != dominant_faction):
                        p.set_controlled_by(None)
                        p.reset_scores()

    def capture_isolated_planets(self):
        planets_by_faction = self._get_planets_by_controlling_faction()
        if len(planets_by_faction) != 2:
            # too difficult to work out who to give the isolated planets too
            return

        for faction, capital in self._capitals_by_faction.items():
            planet_ids = [p.get_id() for p in planets_by_faction[faction]]
            g = self._make_sub_graph(planet_ids)
            for pid in planet_ids:
                connectivity = networkx.node_connectivity(g, capital.get_id(), pid)
                if connectivity == 0:
                    other_faction = [f for f in self._capitals_by_faction.keys() if f != faction][0]
                    isolated_planet = self._planets_by_id[pid]
                    isolated_planet.set_controlled_by(other_faction)
                    for p in self._neighbours_by_name[isolated_planet.get_name()]:
                        p.set_controlled_by(other_faction)

    def get_uncaptured_capitals(self) -> List[Planet]:
        return [planet for faction, planet in self._capitals_by_faction.items()
                if planet.get_controlled_by() == faction]

    def _get_planets_by_controlling_faction(self):
        planets_by_faction = defaultdict(list)
        for id, planet in self._planets_by_id.items():
            faction = planet.get_controlled_by()
            if faction is not None:
                planets_by_faction[faction] += [planet]
        return planets_by_faction

    def _make_sub_graph(self, planet_ids: List[int]):
        graph = networkx.Graph()
        graph.add_nodes_from(planet_ids)
        graph.add_edges_from([(id1, id2)
                              for id1, id2 in self._jump_gates.items()
                              if id1 in planet_ids and id2 in planet_ids])
        return graph