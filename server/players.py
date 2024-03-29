from contextlib import suppress
from enum import Enum, unique
from typing import Optional, Union

from server.config import config
from server.rating import PlayerRatings, RatingType, RatingTypeMap

from .factions import Faction
from .protocol import DisconnectedError
from .weakattr import WeakAttribute


@unique
class PlayerState(Enum):
    IDLE = 1
    HOSTING = 2
    JOINING = 3
    HOSTED = 4
    JOINED = 5
    PLAYING = 6
    SEARCHING_LADDER = 7
    STARTING_AUTOMATCH = 8


class Player:
    """
    Standard player object used for representing signed-in players.

    In the context of a game, the Game object holds game-specific
    information about players.
    """

    lobby_connection = WeakAttribute["LobbyConnection"]()
    game = WeakAttribute["Game"]()
    game_connection = WeakAttribute["GameConnection"]()

    def __init__(
        self,
        login: str = None,
        session: int = 0,
        ip = None,
        player_id: int = 0,
        ratings=None,
        clan=None,
        game_count=None,
        lobby_connection: Optional["LobbyConnection"] = None
    ) -> None:
        self._faction = Faction.arm

        self.id = player_id
        self.login = login
        self.alias = login
        self.ip = ip

        # The player_id of the user in the `login` table of the database.
        self.session = session

        self.ratings = PlayerRatings(
            lambda: (config.START_RATING_MEAN, config.START_RATING_DEV)
        )
        if ratings is not None:
            self.ratings.update(ratings)

        self.game_count = RatingTypeMap(int)
        if game_count is not None:
            self.game_count.update(game_count)

        # social
        self.avatar = None
        self.clan = clan
        self.country = None

        self.friends = set()
        self.foes = set()

        self.user_groups = set()

        self.state = PlayerState.IDLE
        self._afk_seconds = 0
        # nasty hack work-around ICE adapter dropping 2nd arg of GameState messages.
        # we set substate using GameOption instead and examine it when we receive the GameState
        # NB this reflects state of individual player's game, not hosts's game
        self.own_game_substate = None

        if lobby_connection is not None:
            self.lobby_connection = lobby_connection

    @property
    def faction(self) -> Faction:
        return self._faction

    @property
    def address(self) -> str:
        return self.ip

    def set_afk_seconds(self, afk_seconds: int):
        self._afk_seconds = afk_seconds

    def get_afk_seconds(self) -> int:
        return self._afk_seconds

    @faction.setter
    def faction(self, value: Union[str, int, Faction]) -> None:
        if isinstance(value, Faction):
            self._faction = value
        else:
            self._faction = Faction.from_value(value)

    def power(self) -> int:
        """An artifact of the old permission system. The client still uses this
        number to determine if a player gets a special category in the user list
        such as "Moderator"
        """
        if self.is_admin():
            return 2
        if self.is_moderator():
            return 1

        return 0

    def is_admin(self) -> bool:
        return "faf_server_administrators" in self.user_groups

    def is_moderator(self) -> bool:
        return "faf_moderators_global" in self.user_groups

    async def send_message(self, message: dict) -> None:
        """
        Try to send a message to this player.

        :raises: DisconnectedError if the player has disconnected.
        """
        if self.lobby_connection is None:
            raise DisconnectedError("Player has disconnected!")

        await self.lobby_connection.send(message)

    def write_message(self, message: dict) -> None:
        """
        Try to queue a message to be sent to this player.

        Does nothing if the player has disconnected.
        """
        if self.lobby_connection is None:
            return

        with suppress(DisconnectedError):
            self.lobby_connection.write(message)

    def to_dict(self):
        """
        Return a dictionary representing this player object
        :return:
        """

        def filter_none(t):
            _, v = t
            return v is not None

        player_state = {
            PlayerState.IDLE: "idle",
            PlayerState.HOSTING: "hosting",
            PlayerState.JOINING: "joining",
            PlayerState.HOSTED: "hosted",
            PlayerState.JOINED: "joined",
            PlayerState.PLAYING: "playing",
            PlayerState.SEARCHING_LADDER: "searching_ladder"
        }.get(self.state, "idle")

        return dict(
            filter(
                filter_none, (
                    ("id", self.id),
                    ("login", self.login),
                    ("alias", self.alias),
                    ("avatar", self.avatar),
                    ("country", self.country),
                    ("clan", self.clan),
                    ("ratings", {
                        rating_type: {
                            "rating": self.ratings[rating_type],
                            "number_of_games": self.game_count[rating_type]
                        }
                        for rating_type in self.ratings
                    }),
                    ("state", player_state),
                    ("afk_seconds", self._afk_seconds),
                    ("current_game_uid", self.game.id if self.game else -1),
                    ("number_of_games", self.game_count[RatingType.GLOBAL]),
                )
            )
        )

    def __str__(self) -> str:
        return (f"Player({self.login}, {self.id}, "
                f"{self.ratings[RatingType.GLOBAL]}, ")

    def __repr__(self) -> str:
        return (f"Player(login={self.login}, session={self.session}, "
                f"id={self.id}, ratings={dict(self.ratings)}, "
                f"clan={self.clan}, game_count={dict(self.game_count)})")

    def __hash__(self) -> int:
        return self.id

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.id == other.id
