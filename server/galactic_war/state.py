from trueskill import Rating

from .planet import Planet
from collections import defaultdict
import networkx
from typing import List, Dict

from .. import config
from ..decorators import with_logger
from ..factions import Faction
from ..games.game_results import GameOutcome
from ..games.typedefs import EndedGameInfo, ValidityState, OutcomeLikelihoods
from ..matchmaker import MatchmakerQueue
from ..rating import RatingType
from ..rating_service.typedefs import PlayerID, TeamID, RankedRating

import scipy.stats

class InvalidGalacticWarGame(Exception):
    """ raised by validate_game when illegal game settings are found """

@with_logger
class GalacticWarState(object):

    def __init__(self, data, default_scenario_name: str = None):
        if default_scenario_name is not None and ("label" not in data or len(data["label"]) == 0):
            data["label"] = default_scenario_name

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
            self._neighbours_by_name[target_planet.get_name()] += [source_planet]

    def get_data(self):
        return self._data

    def get_label(self):
        return self._data["label"]

    def validate_game(self, game_info: EndedGameInfo):
        try:
            planet = self._planets_by_name[game_info.galactic_war_planet_name]
        except KeyError:
            raise InvalidGalacticWarGame(f"'{game_info.galactic_war_planet_name}' is not part of the current Galactic War scenario")

        if planet.get_map() != game_info.map_name:
            raise InvalidGalacticWarGame(f"'{planet.get_name()}' should be played on map '{planet.get_map()}', not '{game_info.map_name}'")

        if config.GALACTIC_WAR_REQUIRE_CORRECT_MOD and planet.get_mod() != game_info.game_mode:
            raise InvalidGalacticWarGame(f"'{planet.get_name()}' should be played with mod '{planet.get_mod()}', not '{game_info.game_mode}'")

        factions_by_team = defaultdict(list)
        for player_info in game_info.ended_game_player_summary:
            factions_by_team[player_info.team_id] += [player_info.faction]
            if factions_by_team[player_info.team_id][0] != player_info.faction:
                raise InvalidGalacticWarGame(f"Galactic War should be played one faction versus another")

        if len(factions_by_team) != 2:
            raise InvalidGalacticWarGame("Galactic War should be played with exactly two teams")

        team_factions = [factions[0] for factions in factions_by_team.values()]
        if team_factions[0] == team_factions[1]:
            raise InvalidGalacticWarGame("Galactic War should be played with opposing factions")

        if game_info.rating_type is None or game_info.rating_type == RatingType.GLOBAL:
            raise InvalidGalacticWarGame("Galactic War should be played with ranked settings")

        if game_info.validity != ValidityState.VALID:
            raise InvalidGalacticWarGame(game_info.validity.name)

        if planet.get_controlled_by() is not None:
            raise InvalidGalacticWarGame(f"{planet.get_name()} ({planet.get_controlled_by().name} controlled) is not contested")

        neighbouring_planet_factions = [p.get_controlled_by() for p in self._neighbours_by_name[planet.get_name()]]
        for faction in team_factions:
            if planet.get_capital_of() != faction and faction not in neighbouring_planet_factions:
                raise InvalidGalacticWarGame(f"{faction.name} does not have connectivity to planet '{planet.get_name()}'")

        return

    def update_scores(self,
                      game_info: EndedGameInfo,
                      old_ratings: Dict[PlayerID, RankedRating],
                      new_ratings: Dict[PlayerID, Rating],
                      team_outcome_likelihoods: Dict[TeamID, OutcomeLikelihoods]):
        planet = self._planets_by_name[game_info.galactic_war_planet_name]

        # each player stakes an amount proportional to their team's win likelihood
        if config.GALACTIC_WAR_STAKES_STRATEGY == "rank":
            stakes = self._calculate_stakes_from_rank(game_info, old_ratings)
        elif config.GALACTIC_WAR_STAKES_STRATEGY == "rating":
            stakes = self._calculate_stakes_from_rating(game_info, team_outcome_likelihoods)
        else:
            stakes = self._calculate_stakes_from_rating(game_info, team_outcome_likelihoods)

        # players stakes are returned depending on outcome
        returned_stakes = {player_info.player_id: {
            GameOutcome.VICTORY: stakes[player_info.player_id],
            GameOutcome.DRAW: stakes[player_info.player_id] / 2.0,
            GameOutcome.DEFEAT: 0.0
        }[player_info.outcome] for player_info in game_info.ended_game_player_summary}

        # stakes lost by losers are distributed to winners
        total_lost_stakes = sum(stakes.values()) - sum(returned_stakes.values())
        team_size = len(stakes) // 2
        winners_gains = {player_info.player_id: {
            GameOutcome.VICTORY: total_lost_stakes / team_size,
            GameOutcome.DRAW: 0.0,
            GameOutcome.DEFEAT: 0.0
        }[player_info.outcome] for player_info in game_info.ended_game_player_summary}

        # execute adjustments to score
        for player_info in game_info.ended_game_player_summary:
            pid = player_info.player_id
            belligerent_attribution_adjustment = winners_gains[pid] + returned_stakes[pid] - stakes[pid]
            if config.GALACTIC_WAR_WINNER_TAKES_THE_POT:
                planet_adjustment = winners_gains[pid] + returned_stakes[pid] - stakes[pid]
            else:
                planet_adjustment = returned_stakes[pid] - stakes[pid]

            self._logger.info("[update_scores] player %d of %s. stake=%.1f, returned=%.1f, winnings=%.1f, planet_adj=%.1f, belligerent_adj=%.1f",
                              pid, player_info.faction.name, stakes[pid], returned_stakes[pid], winners_gains[pid], planet_adjustment, belligerent_attribution_adjustment)

            planet.set_score(player_info.faction, planet.get_score(player_info.faction) + planet_adjustment)
            planet.adjust_belligerent(player_info.player_id, player_info.faction, belligerent_attribution_adjustment)

    def _calculate_stakes_from_rating(self,
                                      game_info: EndedGameInfo,
                                      team_outcome_likelihoods: Dict[TeamID, OutcomeLikelihoods]) -> Dict[PlayerID, float]:

        return {player_info.player_id: team_outcome_likelihoods[player_info.team_id].pwin * config.GALACTIC_WAR_MAX_SCORE
                  for player_info in game_info.ended_game_player_summary}


    def _calculate_stakes_from_rank(self,
                                    game_info: EndedGameInfo,
                                    old_ratings: Dict[PlayerID, RankedRating]) -> Dict[PlayerID, float]:

        team_ids = list({player_info.team_id for player_info in game_info.ended_game_player_summary})
        assert(len(team_ids) == 2)

        player_ids_by_team = {
            tid: [player_info.player_id for player_info in game_info.ended_game_player_summary if player_info.team_id == tid]
            for tid in team_ids
        }

        team_size = len(game_info.ended_game_player_summary) // 2
        max_stake_per_opponent = config.GALACTIC_WAR_MAX_SCORE / team_size
        stakes = {player_info.player_id: 0. for player_info in game_info.ended_game_player_summary}
        for pid1 in player_ids_by_team[team_ids[0]]:
            for pid2 in player_ids_by_team[team_ids[1]]:
                if old_ratings[pid1].leaderboard_size < 10:
                    stakes[pid1] += max_stake_per_opponent / 2.
                    stakes[pid2] += max_stake_per_opponent / 2.

                elif abs(old_ratings[pid1].penis_points - old_ratings[pid2].penis_points) < 1.:
                    stakes[pid1] += max_stake_per_opponent / 2.
                    stakes[pid2] += max_stake_per_opponent / 2.

                else:
                    rank_difference = (old_ratings[pid2].rank - old_ratings[pid1].rank) / old_ratings[pid1].leaderboard_size
                    stakes[pid1] += scipy.stats.norm.cdf(rank_difference / config.GALACTIC_WAR_STAKES_RANK_FACTOR) * max_stake_per_opponent
                    stakes[pid2] += scipy.stats.norm.cdf(-rank_difference / config.GALACTIC_WAR_STAKES_RANK_FACTOR) * max_stake_per_opponent

        return stakes


    def update_front_lines(self, planet=None):
        changes_made = 0
        if planet is None:
            # do planets with higher scores first so if theres a conflict, the higher-scored planet gets precedence
            contested_planets = [p for pid, p in self._planets_by_id.items() if p.get_controlled_by() is None]
            contested_planets.sort(key=lambda p: max(p.get_ro_scores().values()), reverse=True)
            return sum([self.update_front_lines(p) for p in contested_planets])

        else:
            dominant_faction = planet.get_dominant_faction()
            if dominant_faction is not None:
                self._logger.info(f"[update_front_lines] capturing {planet.get_name()} for {dominant_faction.name} because is dominating")
                planet.set_controlled_by(dominant_faction)
                for p in self._neighbours_by_name[planet.get_name()]:
                    f = p.get_dominant_faction()
                    c = p.get_controlled_by()
                    if (f is not None and f != dominant_faction):
                        self._logger.info(f"[update_front_lines] contesting {p.get_name()}({f.name} dominant) because neighbours with {planet.get_name()}({dominant_faction.name} captured)")
                        p.set_controlled_by(None)
                        p.reset_scores()
                        changes_made += 1
                    elif (c is not None and c != dominant_faction):
                        self._logger.info(f"[update_front_lines] contesting {p.get_name()}({c.name} controlled) because neighbours with {planet.get_name()}({dominant_faction.name} captured)")
                        p.set_controlled_by(None)
                        p.reset_scores()
                        changes_made += 1
        return changes_made

    def capture_uncontested_planets(self):
        """
        :brief: find contested planets that are neighboured by one faction only.  Hand such planets over to that faction
        """
        changes_made = 0
        for planet in self._planets_by_id.values():
            if planet.get_controlled_by() is None and planet.get_capital_of() is None:
                factions = list(set([p.get_controlled_by()
                                     for p in self._neighbours_by_name[planet.get_name()]
                                     if p.get_controlled_by() is not None]))
                if len(factions) == 1:
                    self._logger.info(f"[capture_uncontested_planets] capturing {planet.get_name()} for {factions[0].name} because no one else is neighbouring")
                    planet.set_controlled_by(factions[0])
                    changes_made += 1

        return changes_made

    def capture_isolated_planets(self):
        """
        :brief: find planets that are controlled by some faction, but which don't have a path to their capital through
        other controlled planets. Take those planets away from that faction
        """
        changes_made = 0
        planets_by_faction = self._get_planets_by_controlling_faction()
        if len(planets_by_faction) != 2:
            # too difficult to work out who to give the isolated planets too
            return changes_made

        for faction, capital in self._capitals_by_faction.items():
            planet_ids = [p.get_id() for p in planets_by_faction[faction]]
            g = self._make_sub_graph(planet_ids)
            for pid in planet_ids:
                if pid == capital.get_id():
                    continue

                try:
                    connectivity = 0
                    if capital.get_id() in planet_ids:
                        connectivity = networkx.node_connectivity(g, capital.get_id(), pid)

                    if connectivity == 0:
                        other_faction = [f for f in self._capitals_by_faction.keys() if f != faction][0]
                        isolated_planet = self._planets_by_id[pid]
                        self._logger.info(f"[capture_isolated_planets] capturing {isolated_planet.get_name()} for {other_faction.name} because is isolated from {faction.name}'s capital")
                        isolated_planet.set_controlled_by(other_faction)
                        changes_made += 1

                except networkx.NetworkXError as e:
                    self._logger.warning(f"[capture_isolated_planets] unable to find connectivity from capital={capital.get_id()} to pid={pid}: {str(e)}")

        return changes_made

    def get_capitals(self, standing=True, contested=True, captured=True) -> List[Planet]:
        return [planet for faction, planet in self._capitals_by_faction.items()
                if standing and planet.get_controlled_by() == faction or
                contested and planet.get_controlled_by() is None or
                captured and planet.get_controlled_by() != faction]

    def get_uncontested_planets(self) -> List[Planet]:
        return [planet for planet in self._planets_by_id.values()
                if planet.get_controlled_by() is not None]

    def assign_two_capitals(self):
        pids = [pid for pid in self._planets_by_id.keys()]
        G = self._make_sub_graph(pids)
        all_pairs_shortest_path = networkx.all_pairs_shortest_path(G)
        all_pairs_path_length = [(pid1, pid2, len(path12))
                                 for pid1, paths1 in all_pairs_shortest_path
                                 for pid2, path12 in paths1.items()]
        all_pairs_path_length.sort(key=lambda x: x[2])
        capital1_id, capital2_id, _ = all_pairs_path_length[-1]

        for pid, planet in self._planets_by_id.items():
            if pid == capital1_id:
                planet.set_capital_of(Faction.arm)
                planet.set_controlled_by(Faction.arm)
            elif pid == capital2_id:
                planet.set_capital_of(Faction.core)
                planet.set_controlled_by(Faction.core)
            else:
                planet.set_capital_of(None)

    def distribute_planets_to_factions(self):
        pids = [pid for pid in self._planets_by_id.keys()]
        G = self._make_sub_graph(pids)
        shortest_paths_by_capital_id = {
            capital.get_id(): networkx.single_source_shortest_path(G, capital.get_id())
            for capital in self.get_capitals()
        }

        distance_to_capitals_by_pid = {}
        for capital_id, shortest_paths in shortest_paths_by_capital_id.items():
            for planet_id, path in shortest_paths.items():
                try:
                   distance_to_capitals_by_pid[planet_id] += [(capital_id, len(path))]
                except KeyError:
                    distance_to_capitals_by_pid[planet_id] = [(capital_id, len(path))]

        for planet_id, distance_to_capitals in distance_to_capitals_by_pid.items():
            distance_to_capitals.sort(key=lambda x: x[1])
            if distance_to_capitals[0][1] == distance_to_capitals[1][1]:
                self._planets_by_id[planet_id].set_controlled_by(None)
                self._planets_by_id[planet_id].reset_scores()
            else:
                closest_capital_planet = self._planets_by_id[distance_to_capitals[0][0]]
                self._planets_by_id[planet_id].set_controlled_by(closest_capital_planet.get_controlled_by())

    def seperate_abutting_factions(self):
        for name, planet in self._planets_by_name.items():
            for neighbour in self._neighbours_by_name[name]:
                if planet.get_controlled_by() is not None and neighbour.get_controlled_by() is not None and planet.get_controlled_by() != neighbour.get_controlled_by():
                    planet.set_controlled_by(None)
                    planet.reset_scores()

    def ensure_ranked_maps(self, matchmaker_queues: Dict[str, MatchmakerQueue]):
        self._logger.info(f"[ensure_ranked_maps] queues={matchmaker_queues.keys()}")
        chosen_maps = list(set([planet.get_map() for planet in self._planets_by_name.values()]))
        map_pool_map_names = {}
        for planet in self._planets_by_name.values():
            for queue in matchmaker_queues.values():
                if queue.featured_mod == planet.get_mod() and queue.team_size == 1:
                    map_pool = queue.get_map_pool_for_rating(1500)
                    if map_pool.name not in map_pool_map_names.keys():
                        map_pool_map_names[map_pool.name] = set([m.name for m in map_pool.maps.values()])
                    if planet.get_map() not in map_pool_map_names[map_pool.name]:
                        random_map = map_pool.choose_map(chosen_maps)
                        self._logger.info(f"[ensure_ranked_maps] planet:{planet.get_name()}, mod:{planet.get_mod()}, "
                                          f"map:{planet.get_map()}. Map not found in map pool.  Reassigning to map:"
                                          f"{random_map.name}")
                        chosen_maps += [random_map.id]
                        planet.set_map(random_map.name)
                    break

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
                              for id1, id2 in self._jump_gates
                              if id1 in planet_ids and id2 in planet_ids])
        return graph
