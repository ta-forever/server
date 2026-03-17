import bisect
import math
import random
from itertools import cycle

import sqlalchemy
from trueskill import Rating

from .planet import Planet
from collections import defaultdict
import networkx
import re
from typing import List, Dict, Tuple, Set

from .roman_planet_name import roman_planet_name
from .typedefs import GwPlayerScore, GwGalaxyConfig, GwMapSelectStrategy
from ..config import config
from ..db import FAFDatabase
from ..player_service import PlayerService
from ..decorators import with_logger
from ..factions import Faction
from ..games.game_results import GameOutcome
from ..games.typedefs import EndedGameInfo, ValidityState, OutcomeLikelihoods, EndedGamePlayerSummary
from ..matchmaker import MatchmakerQueue
from ..rating import RatingType
from ..rating_service.typedefs import PlayerID, TeamID, RankedRating
import scipy.stats

from ..types import Map


class InvalidGalacticWarGame(Exception):
    """ raised by validate_game when illegal game settings are found """

@with_logger
class GalacticWarState(object):

    def __init__(self, data, galaxy_config: GwGalaxyConfig, default_scenario_name: str = None):

        data["technical_name"] = galaxy_config.technical_name
        data["display_name"] = galaxy_config.display_name
        data["rank_thresholds"] = config.GALACTIC_WAR_RANK_THRESHOLDS
        data["dominance_threshold"] = config.GALACTIC_WAR_DOMINANCE_THRESHOLD

        if galaxy_config.map_select_strategy == GwMapSelectStrategy.REGEX:
            data["map_select_strategy"] = "REGEX"
            data["map_select_regexes"] = {k: v.map_select_regexes for k, v in galaxy_config.mods.items()}

        else: # GwMapSelectStrategy.MAP_POOL
            data["map_select_strategy"] = "MAP_POOL"
            data["map_select_mmq_id"] = {k: v.map_select_mmq_id for k, v in galaxy_config.mods.items()}

        data["factions"] = [k.name for k in galaxy_config.rank_avatar_ids.keys()]

        if default_scenario_name is not None and ("label" not in data or len(data["label"]) == 0):
            data["label"] = default_scenario_name

        if not "players" in data.keys():
            data["players"] = {}

        data["players"] = {
            int(pid_string): {
                faction_name: player_scores if isinstance(player_scores, GwPlayerScore) else GwPlayerScore.from_dict(player_scores)
                for faction_name, player_scores in v.items()
            }
            for pid_string, v in data["players"].items()
        }

        self._data = data

        mod_names = [cfg.technical_name for cfg in galaxy_config.mods.values()]
        n_planets = len(data["node"])
        n_dup = int(math.ceil(n_planets / len(mod_names)))
        mod_names = [x for x in mod_names for _ in range(n_dup)]
        random.shuffle(mod_names)

        planets = [Planet(v, mod_name) for v, mod_name in zip(data["node"], mod_names)]

        self._planets_by_id = {p.get_id(): p for p in planets}
        self._planets_by_name = {p.get_name(): p for p in planets}
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

    def validate_game(self, game_info: EndedGameInfo, player_service: PlayerService):
        try:
            planet = self._planets_by_name[game_info.galactic_war_planet_name]
        except KeyError:
            raise InvalidGalacticWarGame(f"'{game_info.galactic_war_planet_name}' is not part of the current Galactic War scenario")

        if planet.get_map() != game_info.map_name:
            raise InvalidGalacticWarGame(f"'{planet.get_name()}' must be played on map '{planet.get_map()}', not '{game_info.map_name}'")

        if config.GALACTIC_WAR_REQUIRE_CORRECT_MOD and planet.get_mod() != game_info.game_mode:
            raise InvalidGalacticWarGame(f"'{planet.get_name()}' must be played with mod '{planet.get_mod()}', not '{game_info.game_mode}'")

        factions_by_team = defaultdict(list)
        for player_info in game_info.ended_game_player_summary:
            factions_by_team[player_info.team_id].append(player_info.faction)

        if len(factions_by_team) != 2:
            raise InvalidGalacticWarGame("Galactic War must be played with exactly two teams")

        for team_id, factions in factions_by_team.items():
            unique_factions = set(factions)
            if len(unique_factions) > 1:
                raise InvalidGalacticWarGame(f"For Galactic War, each team must use a single faction")

        team_factions = {factions[0] for factions in factions_by_team.values()}
        if len(team_factions) != 2:
            raise InvalidGalacticWarGame("Galactic War must be played with opposing factions")

        bad_faction_msgs = []
        for player_info in game_info.ended_game_player_summary:
            player_scores_by_faction = [(f, self.get_player_score(player_info.player_id, f)) for f in Faction]
            best_faction, best_score = max(player_scores_by_faction, key=lambda item: (item[1].cum_winning_scores, item[1].wins + item[1].losses))
            if (best_score.wins > 0 or best_score.losses > 0) and best_faction != player_info.faction:
                player = player_service.get_player(player_info.player_id)
                player_name = player.login if player else str(player_info.player_id)
                bad_faction_msgs.append(f"{player_name} played for {player_info.faction.name.upper()} but previously enlisted with {best_faction.name.upper()}")
        if len(bad_faction_msgs) > 0:
            msg = '; '.join(bad_faction_msgs)
            raise InvalidGalacticWarGame('; '.join(bad_faction_msgs))

        if game_info.rating_type is None or game_info.rating_type == RatingType.GLOBAL:
            raise InvalidGalacticWarGame("Galactic War must be played with ranked settings")

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
            stakes, PLANET_ADJ = self._calculate_stakes_from_rank_tier(game_info.ended_game_player_summary)
        elif config.GALACTIC_WAR_STAKES_STRATEGY == "rating":
            stakes, PLANET_ADJ = self._calculate_stakes_from_rating(game_info.ended_game_player_summary, team_outcome_likelihoods)
        else:
            stakes, PLANET_ADJ = self._calculate_stakes_from_rating(game_info.ended_game_player_summary, team_outcome_likelihoods)

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
            planet_adjustment = returned_stakes[pid] - stakes[pid]
            if planet_adjustment < 0. and PLANET_ADJ is not None:
                planet_adjustment = -PLANET_ADJ

            self._logger.info("[update_scores] player %d of %s. stake=%.1f, returned=%.1f, winnings=%.1f, planet_adj=%.1f, belligerent_adj=%.1f",
                              pid, player_info.faction.name, stakes[pid], returned_stakes[pid], winners_gains[pid], planet_adjustment, belligerent_attribution_adjustment)

            planet.set_score(player_info.faction, planet.get_score(player_info.faction) + planet_adjustment)
            planet.adjust_belligerent(player_info.player_id, player_info.faction, belligerent_attribution_adjustment)
            self._adjust_player(player_info.player_id, player_info.faction.name, belligerent_attribution_adjustment)

    def get_player_score(self, pid: int, faction: Faction) -> GwPlayerScore:
        if not pid in self._data["players"]:
            return GwPlayerScore()

        player_data = self._data["players"][pid]
        if not faction.name in player_data:
            return GwPlayerScore()

        return player_data[faction.name]

    def _adjust_player(self, pid: int, faction_name: str, score_adj: float):
        if not pid in self._data["players"]:
            self._data["players"][pid] = {}

        player_data = self._data["players"][pid]
        if not faction_name in player_data:
            player_data[faction_name] = GwPlayerScore()

        player_scores = player_data[faction_name]
        if score_adj > 0.:
            player_scores.wins += 1
            player_scores.cum_winning_scores += score_adj
        elif score_adj < 0.:
            player_scores.losses += 1
            player_scores.cum_losing_scores += score_adj

    def _get_leaderboard(self) -> List[Tuple[int, GwPlayerScore]]:
        return sorted(
            (
                (pid, max(scores.values(), key=lambda s: (
                    s.cum_winning_scores,
                    s.cum_losing_scores,
                    s.wins,
                    -s.losses
                )))
                for pid, scores in self._data["players"].items()
            ),
            key=lambda item: (
                item[1].cum_winning_scores,
                item[1].cum_losing_scores,
                item[1].wins,
                -item[1].losses,
            ),
            reverse=True
        )

    def _calculate_stakes_from_rating(self,
                                      ended_game_player_summary: List[EndedGamePlayerSummary],
                                      team_outcome_likelihoods: Dict[TeamID, OutcomeLikelihoods]) \
            -> Tuple[Dict[PlayerID, float], None]:

        planet_adj = None  # revert to the loser's stakes
        return {player_info.player_id: team_outcome_likelihoods[player_info.team_id].pwin * config.GALACTIC_WAR_MAX_SCORE
                  for player_info in ended_game_player_summary}, planet_adj


    def _calculate_stakes_from_rank_tier(self, ended_game_player_summary: List[EndedGamePlayerSummary]) \
            -> Tuple[Dict[PlayerID, float], float]:

        team_ids = list({player_info.team_id for player_info in ended_game_player_summary})
        assert(len(team_ids) == 2)

        player_ids_by_team = {
            tid: [player_info.player_id for player_info in ended_game_player_summary if player_info.team_id == tid]
            for tid in team_ids
        }

        def rank_tier_for_score(score: GwPlayerScore):
            return bisect.bisect_right(config.GALACTIC_WAR_RANK_THRESHOLDS, score.cum_winning_scores)

        leaderboard = self._get_leaderboard()
        rank_by_pid = {pid: rank_tier_for_score(score) for pid, score in leaderboard}
        NUM_RANK_TIERS = 1 + len(config.GALACTIC_WAR_RANK_THRESHOLDS)

        team_size = len(ended_game_player_summary) // 2
        max_stake_per_opponent = config.GALACTIC_WAR_MAX_SCORE / team_size

        def sigmoid(diff: float):
            return max_stake_per_opponent / (1. + math.exp(-diff/config.GALACTIC_WAR_STAKES_RANK_FACTOR))

        stakes = {player_info.player_id: 0. for player_info in ended_game_player_summary}
        for pid1 in player_ids_by_team[team_ids[0]]:
            rank1 = rank_by_pid.get(pid1, 0)
            for pid2 in player_ids_by_team[team_ids[1]]:
                rank2 = rank_by_pid.get(pid2, 0)
                rank_difference = (rank1 - rank2)
                stakes[pid1] += sigmoid(rank_difference)
                stakes[pid2] += sigmoid(-rank_difference)

        min_rank_in_game = min(rank_by_pid.values()) if len(rank_by_pid) > 0 else 0
        min_adj, max_adj = config.GALACTIC_WAR_MIN_MAX_PLANET_ADJ
        planet_adj = min_adj + (max_adj - min_adj) * min_rank_in_game / max(1, (NUM_RANK_TIERS - 1))
        planet_adj = min(planet_adj, config.GALACTIC_WAR_MAX_SCORE)

        return stakes, planet_adj

    def _calculate_stakes_from_leaderboard_position(self, ended_game_player_summary: List[EndedGamePlayerSummary]) \
            -> Tuple[Dict[PlayerID, float], float]:

        team_ids = list({player_info.team_id for player_info in ended_game_player_summary})
        assert(len(team_ids) == 2)

        player_ids_by_team = {
            tid: [player_info.player_id for player_info in ended_game_player_summary if player_info.team_id == tid]
            for tid in team_ids
        }

        leaderboard = self._get_leaderboard()
        rank_by_pid = {pid: n for n, (pid, score) in enumerate(leaderboard)}
        NUM_RANKS = len(leaderboard)

        team_size = len(ended_game_player_summary) // 2
        max_stake_per_opponent = config.GALACTIC_WAR_MAX_SCORE / team_size
        stakes = {player_info.player_id: 0. for player_info in ended_game_player_summary}
        for pid1 in player_ids_by_team[team_ids[0]]:
            rank1 = rank_by_pid.get(pid1, NUM_RANKS // 2)
            for pid2 in player_ids_by_team[team_ids[1]]:
                rank2 = rank_by_pid.get(pid2, NUM_RANKS // 2)
                rank_difference = (rank2 - rank1) / NUM_RANKS if NUM_RANKS >= 10 else 0
                stakes[pid1] += scipy.stats.norm.cdf(rank_difference / config.GALACTIC_WAR_STAKES_RANK_FACTOR) * max_stake_per_opponent
                stakes[pid2] += scipy.stats.norm.cdf(-rank_difference / config.GALACTIC_WAR_STAKES_RANK_FACTOR) * max_stake_per_opponent

        min_rank_in_game = min(rank_by_pid.values())
        min_adj, max_adj = config.GALACTIC_WAR_MIN_MAX_PLANET_ADJ
        planet_adj = min_adj + (max_adj - min_adj) * min_rank_in_game / max(1, (NUM_RANKS-1))

        return stakes, planet_adj

    async def _get_player_name(self, database: FAFDatabase, player_id) -> str:
        async with database.acquire() as conn:
            result = await conn.execute(sqlalchemy.sql.text(
                "SELECT login from login WHERE id = :player_id"), player_id=player_id)
            row = result.fetchone()
            return row[0] if row else None

    async def update_front_lines(self, database: FAFDatabase, planet=None):
        changes_made = 0
        if planet is None:
            # do planets with higher scores first so if there's a conflict, the higher-scored planet gets precedence
            contested_planets = [p for pid, p in self._planets_by_id.items() if p.get_controlled_by() is None]
            contested_planets.sort(key=lambda p: max(p.get_ro_scores().values()), reverse=True)
            return sum([await self.update_front_lines(database, planet=p) for p in contested_planets])

        else:
            dominant_faction = planet.get_dominant_faction()
            if dominant_faction is not None:
                self._logger.info(f"[update_front_lines] capturing {planet.get_name()} for {dominant_faction.name} because is dominating")
                planet.set_controlled_by(dominant_faction)

                heroic_player_id, cum_winning_score = planet.get_most_heroic_player(dominant_faction)
                if cum_winning_score > 0:
                    heroic_player_name = await self._get_player_name(database, heroic_player_id)
                    if heroic_player_name:
                        old_planet_name = planet.get_name()
                        new_planet_name = roman_planet_name(heroic_player_name, self._planets_by_name.keys())
                        self._logger.info(f"[update_front_lines] renaming from {old_planet_name} to {new_planet_name} to honour {heroic_player_name}")
                        planet.set_name(new_planet_name)
                        self._planets_by_name[new_planet_name] = self._planets_by_name.pop(old_planet_name)
                        self._neighbours_by_name[new_planet_name] = self._neighbours_by_name.pop(old_planet_name)

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

    def assign_two_capitals(self, galaxy_config=None):
        # Try explicit named capitals from per-galaxy config first.
        arm_planet = None
        core_planet = None
        if galaxy_config is not None:
            arm_name = galaxy_config.arm_capital
            core_name = galaxy_config.core_capital
            if arm_name and core_name:
                arm_planet = self._planets_by_name.get(arm_name)
                core_planet = self._planets_by_name.get(core_name)
                if arm_planet is None or core_planet is None:
                    self._logger.warning(
                        "[assign_two_capitals] named capitals not found in scenario "
                        "(arm='%s' found=%s, core='%s' found=%s); falling back to distance search",
                        arm_name, arm_planet is not None,
                        core_name, core_planet is not None,
                    )
                    arm_planet = core_planet = None

        if arm_planet is None or core_planet is None:
            # Fall back to the pair of planets with the greatest graph distance.
            pids = [pid for pid in self._planets_by_id.keys()]
            G = self._make_sub_graph(pids)
            all_pairs_shortest_path = networkx.all_pairs_shortest_path(G)
            all_pairs_path_length = [(pid1, pid2, len(path12))
                                     for pid1, paths1 in all_pairs_shortest_path
                                     for pid2, path12 in paths1.items()]
            all_pairs_path_length.sort(key=lambda x: x[2])
            capital1_id, capital2_id, _ = all_pairs_path_length[-1]
            arm_planet = self._planets_by_id[capital1_id]
            core_planet = self._planets_by_id[capital2_id]

        arm_id = arm_planet.get_id()
        core_id = core_planet.get_id()
        for pid, planet in self._planets_by_id.items():
            if pid == arm_id:
                planet.set_capital_of(Faction.arm)
                planet.set_controlled_by(Faction.arm)
            elif pid == core_id:
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

    def separate_abutting_factions(self):
        for name, planet in self._planets_by_name.items():
            for neighbour in self._neighbours_by_name[name]:
                if planet.get_controlled_by() is not None and neighbour.get_controlled_by() is not None and planet.get_controlled_by() != neighbour.get_controlled_by():
                    planet.set_controlled_by(None)
                    planet.reset_scores()

    def get_map_pool(self,
                     mod_technical_name: str,
                     matchmaker_queues: Dict[str, MatchmakerQueue],
                     all_ranked_maps: List[Map]) -> Set[str]:

        galaxy_config = GwGalaxyConfig.from_dict_list(config.GALACTIC_WAR_GALAXIES).get(self._data["technical_name"], None)
        if galaxy_config is None:
            raise ValueError(f"Galaxy {self._data["technical_name"]} not found")

        if galaxy_config.map_select_strategy == GwMapSelectStrategy.MAP_POOL:
            mmq_id = galaxy_config.mods[mod_technical_name].map_select_mmq_id
            map_pool = [m.name for mmq in matchmaker_queues.values() if mmq.id == mmq_id
                        for mp, _, _ in mmq.map_pools.values()
                        for m in mp.maps.values()]
            if len(map_pool) == 0:
                self._logger.error(f"unable to find a map pool for mod={mod_technical_name}, mmq_id={mmq_id}")
            return set(map_pool)

        else:  # GwMapSelectStrategy.REGEX
            all_map_names = set(m.name for m in all_ranked_maps)
            regexes = []
            mod_config = galaxy_config.mods[mod_technical_name]
            for pattern in mod_config.map_select_regexes:
                try:
                    regexes.append(re.compile(pattern))
                except re.error as e:
                    self._logger.warning("[get_map_pool] Invalid regex for %s/%s: %s (%s)",
                                         galaxy_config.technical_name, mod_config.technical_name, pattern, e)

            filtered_map_names = set()
            for regex in regexes:
                filtered_map_names.update(mn for mn in all_map_names if regex.search(mn))

            return filtered_map_names

    def ensure_allowed_maps(self, allowed_map_names_by_mod: Dict[str, Set[str]], randomise_maps=False):
        self._logger.info(
            "[ensure_allowed_maps] len(allowed_map_names)=%d",
            len(allowed_map_names_by_mod)
        )

        if not allowed_map_names_by_mod:
            return

        normalized_allowed = {
            mod.upper(): set(map_names)
            for mod, map_names in allowed_map_names_by_mod.items()
        }

        shuffled_cycles_by_mod = {
            mod: cycle(random.sample(sorted(map_names), len(map_names)))
            for mod, map_names in normalized_allowed.items()
            if map_names
        }

        for planet in self._planets_by_name.values():
            mod = planet.get_mod().upper()
            allowed_map_names = normalized_allowed.get(mod)

            if not allowed_map_names:
                self._logger.warning(
                    "[ensure_allowed_maps] No maps matched for mod %s on planet %s",
                    mod,
                    planet.get_name()
                )
                continue

            if randomise_maps or planet.get_map() not in allowed_map_names:
                new_map_name = next(shuffled_cycles_by_mod[mod])

                self._logger.info(
                    "[ensure_allowed_maps] setting map for mod %s on planet %s to %s",
                    mod,
                    planet.get_name(),
                    new_map_name
                )

                planet.set_map(new_map_name)

    def on_command_set_map(self, player_id: int, planet_name: str, map_name: str, allowed_maps_by_mod: Dict[str, Set[str]]):
        planet = self._planets_by_name[planet_name]
        controlling_faction = planet.get_controlled_by()
        if controlling_faction is None:
            raise ValueError(f"You cannot change the map for {planet_name} because it is currently contested!")

        heroic_player_id, _ = planet.get_most_heroic_player(controlling_faction)
        if player_id != heroic_player_id:
            raise ValueError(f"You cannot change the map for {planet_name} because you did not personally conquer it!")

        if map_name not in allowed_maps_by_mod[planet.get_mod()]:
            raise ValueError(f"Map '{map_name}' is not allowed for this planet")

        already_planet = [p for p in self._planets_by_id.values() if p.get_map() == map_name]
        if len(already_planet) > 0:
            raise ValueError(f"Map '{map_name}' is already selected on {already_planet[0].get_name()}! Please try another")

        planet.set_map(map_name)

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
