import random

from server.players import Player

from ..factions import Faction


class PartyMember:
    def __init__(self, player: Player):
        self.player = player
        self.factions = [
            Faction.arm,
            Faction.core,
            Faction.gok
        ]

    def set_player_faction(self) -> None:
        assert self.factions, "At least one faction must be allowed!"
        # NOTE: In the far fetched future we may want to limit the list of
        # playable factions for special game modes. For flexibility we will
        # assume for now that the client will take care of this for us.

        self.player.faction = random.choice(self.factions)

    def to_dict(self):
        return {
            "player": self.player.id,
            "alias": self.player.alias,
            "factions": list(faction.name for faction in self.factions)
        }
