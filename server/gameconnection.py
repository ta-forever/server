import asyncio
import contextlib

from sqlalchemy import select, text

from server.db import FAFDatabase

from .abc.base_game import GameConnectionState
from .config import TRACE, config
from .db.models import coop_leaderboard, coop_map, teamkills
from .decorators import with_logger
from .game_service import GameService
from .games import Game, GameError, GameState, ValidityState, Victory
from .player_service import PlayerService
from .players import Player, PlayerState
from .protocol import DisconnectedError, GpgNetServerProtocol, Protocol

class GameStateNotDirty(Exception):
    pass

@with_logger
class GameConnection(GpgNetServerProtocol):
    """
    Responsible for connections to the game, using the GPGNet protocol
    """

    def __init__(
        self,
        database: FAFDatabase,
        game: Game,
        player: Player,
        protocol: Protocol,
        player_service: PlayerService,
        games: GameService,
        state: GameConnectionState = GameConnectionState.INITIALIZING
    ):
        """
        Construct a new GameConnection
        """
        super().__init__()
        self._db = database
        self._logger.debug("GameConnection initializing")

        self.protocol = protocol
        self._state = state
        self.game_service = games
        self.player_service = player_service

        self._player = player
        player.game_connection = self  # Set up weak reference to self
        self._game = game

        self.finished_sim = False

    @property
    def state(self) -> GameConnectionState:
        return self._state

    @property
    def game(self) -> Game:
        return self._game

    @game.setter
    def game(self, val: Game):
        self._game = val

    @property
    def player(self) -> Player:
        return self._player

    @player.setter
    def player(self, val: Player):
        self._player = val

    def is_host(self) -> bool:
        if not self.game or not self.player:
            return False

        return (
            self.player.state in (PlayerState.HOSTING, PlayerState.HOSTED, PlayerState.PLAYING) and
            self.player is self.game.host
        )

    async def send(self, message):
        """
        Send a game message to the client.

        :raises: DisconnectedError

        NOTE: When calling this on a connection other than `self` make sure to
        handle `DisconnectedError`, otherwise failure to send the message will
        cause the caller to be disconnected as well.
        """
        message["target"] = "game"

        self._logger.log(TRACE, ">> %s: %s", self.player.login, message)
        await self.protocol.send_message(message)

    async def _handle_idle_state(self):
        """
        This message is sent by FA when it doesn't know what to do.
        :return: None
        """
        assert self.game
        state = self.player.state

        if state == PlayerState.HOSTING:
            self.game.state = GameState.STAGING
            self._state = GameConnectionState.CONNECTED_TO_HOST
            self.game.add_game_connection(self)
            self.game.host = self.player
        elif state == PlayerState.JOINING:
            return
        else:
            self._logger.error("Unexpected PlayerState: %s", state)
            await self.abort()

    async def _handle_staging_state(self):
        """
        gpgnet4ta has told us it is ready and listening on
        self.player.game_port for UDP (but TA has not yet been launched)
        We determine the connectivity of the peer and respond
        appropriately
        """
        player_state = self.player.state
        if player_state == PlayerState.HOSTING:
            self.game.state = GameState.STAGING
            await self.send_HostGame(self.game.map_name)
            self.game.set_hosted_staging()

        elif player_state == PlayerState.JOINING:
            # If the player is joining, we connect him to host
            # followed by the rest of the players.
            await self.connect_to_host(self.game.host.game_connection)

            if self._state is GameConnectionState.ENDED:
                # We aborted while trying to connect
                return

            self._state = GameConnectionState.CONNECTED_TO_HOST

            try:
                self.game.add_game_connection(self)
            except GameError as e:
                if self.player.lobby_connection:
                    await self.player.lobby_connection.send({
                        "command": "notice",
                        "style": "game_join_fail",
                        "text": f"Sorry, you can't join this game: {e}"
                    })
                await self.abort(f"GameError while joining {self.game.id}: {e}")
                return

            tasks = []
            for peer in self.game.connections:
                if peer != self and peer.player != self.game.host:
                    self._logger.debug("%s connecting to %s", self.player, peer)
                    tasks.append(self.connect_to_peer(peer))
            await asyncio.gather(*tasks)

    async def _handle_battleroom_state(self):
        if self.player.state == PlayerState.HOSTING:
            self.game.state = GameState.BATTLEROOM
            self.player_service.set_player_state(self.player, PlayerState.HOSTED)
            self.game.set_hosted_battleroom()
        elif self.player.state == PlayerState.JOINING:
            self.player_service.set_player_state(self.player, PlayerState.JOINED)
        else:
            raise GameStateNotDirty

    async def _handle_launching_state(self):
        if self.player.state != PlayerState.HOSTED:
            raise GameStateNotDirty
        self._logger.info( "Launching game %s in state %s", self.game, self.game.state)
        await self.game.on_launching(self.player_service)

    async def _handle_live_state(self):
        if self.is_host():
            self._logger.info( "Launching game %s in state %s", self.game, self.game.state)
            await self.game.on_live()
        else:
            raise GameStateNotDirty

    async def connect_to_host(self, peer: "GameConnection"):
        """
        Connect self to a given peer (host)
        :return:
        """
        if not peer or peer.player.state not in (PlayerState.HOSTING, PlayerState.HOSTED):
            await self.abort("The host left the lobby")
            return

        await self.send_JoinGame(peer.player.address, self.game.get_player_alias(peer.player), peer.player.id)

        if not peer:
            await self.abort("The host left the lobby")
            return

        await peer.send_ConnectToPeer(
            address=self.player.address,
            player_name=self.game.get_player_alias(self.player),
            player_uid=self.player.id,
            offer=True
        )

    async def connect_to_peer(self, peer: "GameConnection"):
        """
        Connect two peers
        :return: None
        """
        if peer is not None:
            await self.send_ConnectToPeer(
                address=peer.player.address,
                player_name=self.game.get_player_alias(peer.player),
                player_uid=peer.player.id,
                offer=True
            )

        if peer is not None:
            with contextlib.suppress(DisconnectedError):
                await peer.send_ConnectToPeer(
                    address=self.player.address,
                    player_name=self.game.get_player_alias(self.player),
                    player_uid=self.player.id,
                    offer=False
                )

    async def handle_action(self, command, args):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        :param command: command type
        :param args: command arguments
        :return: None
        """
        try:
            await COMMAND_HANDLERS[command](self, *args)
        except KeyError:
            self._logger.warning(
                "Unrecognized command %s: %s from player %s",
                command, args, self.player
            )
        except (TypeError, ValueError):
            self._logger.exception("Bad command arguments")
        except ConnectionError as e:
            raise e
        except Exception:  # pragma: no cover
            self._logger.exception("Something awful happened in a game thread!")
            await self.abort()

    async def handle_desync(self, *_args):  # pragma: no cover
        self.game.desyncs += 1

    async def handle_game_option(self, key, value):
        if key == "SubState":
            self.player.own_game_substate = value

        if not self.is_host():
            return

        if key == "Victory":
            self.game.gameOptions["Victory"] = Victory.__members__.get(
                value.upper(), None
            )
        else:
            self.game.gameOptions[key] = value

        if key == "Slots":
            self.game.max_players = int(value)

        elif key == "MapDetails":
            map_name, hpi_archive, crc = value.split(chr(0x1f))[0:3]
            await self.game.fetch_map_file_path(hpi_archive,map_name,crc)

        elif key == "RatingType":
            self.game.rating_type = value
            self.game.rating_type_preferred = value

        elif key == "ReplayDelaySeconds":
            self.game.replay_delay_seconds = int(value)

        elif key == "Title":
            with contextlib.suppress(ValueError):
                self.game.name = value

        self._mark_dirty()

    async def handle_game_metrics(self, key, value):
        ping_table_len_changed = False
        if key == "PlayerPings" and len(value) > 0:
            self._logger.log(TRACE, "[PlayerPings] gameid=%d, playerid=%d, pings=%s", self.game.id, self.player.id, value)
            ping_table_size = len(self.game.player_pings)
            self.game.update_player_pings(self.player.id, value)
            ping_table_len_changed = ping_table_size != len(self.game.player_pings)

        if self.is_host() or (ping_table_len_changed and self.game.host.id not in self.game.player_pings.keys()):
            # @TODO set pings_only=True once everyone has upgraded their clients to cope with it
            self._mark_dirty(only_to_peers=not ping_table_len_changed, pings_only=config.PUBLISH_GAME_INFO_WITH_PINGS_ONLY)

    async def handle_game_mods(self, mode, args):
        if not self.is_host():
            return

        if mode == "activated":
            # In this case args is the number of mods
            if int(args) == 0:
                self.game.mods = {}

        elif mode == "uids":
            uids = str(args).split()
            self.game.mods = {uid: "Unknown sim mod" for uid in uids}
            async with self._db.acquire() as conn:
                result = await conn.execute(
                    text("SELECT `uid`, `name` from `table_mod` WHERE `uid` in :ids"),
                    ids=tuple(uids))
                for row in result:
                    self.game.mods[row.uid] = row.name
        else:
            self._logger.warning("Ignoring game mod: %s, %s", mode, args)
            return

        self._mark_dirty()

    async def handle_player_option(self, player_id, command, value):
        # allow joiner to advertise that they've joined
        # (gpgnet4ta can't work out for the host who's joined until game actually starts)
        # if not self.is_host():
        #     return
        self.game.set_player_option(int(player_id), command, value)
        self._mark_dirty()

    async def handle_ai_option(self, name, key, value):
        if not self.is_host():
            return

        self.game.set_ai_option(str(name), key, value)
        self._mark_dirty()

    async def handle_clear_slot(self, slot):
        if not self.is_host():
            return

        self.game.clear_slot(int(slot))
        self._mark_dirty()

    async def handle_game_result(self, army, result):
        army = int(army)
        result = str(result).lower()
        try:
            label, score = result.split(" ")[-2:]
            await self.game.add_result(self.player.id, army, label, int(score))
        except (KeyError, ValueError):  # pragma: no cover
            self._logger.warning("Invalid result for %s reported: %s", army, result)

    async def handle_operation_complete(self, army, secondary, delta):
        if not int(army) == 1:
            return

        if self.game.validity != ValidityState.COOP_NOT_RANKED:
            return

        secondary, delta = int(secondary), str(delta)
        async with self._db.acquire() as conn:
            # FIXME: Resolve used map earlier than this
            result = await conn.execute(
                select(coop_map.c.id).where(
                    coop_map.c.filename == self.game.map_file_path
                )
            )
            row = result.fetchone()
            if not row:
                self._logger.debug("can't find coop map: %s", self.game.map_file_path)
                return
            mission = row.id

            await conn.execute(
                coop_leaderboard.insert().values(
                    mission=mission,
                    gameuid=self.game.id,
                    secondary=secondary,
                    time=delta,
                    player_count=len(self.game.players),
                )
            )

    async def handle_json_stats(self, stats):
        self.game.report_army_stats(stats)

    async def handle_enforce_rating(self):
        self.game.enforce_rating = True

    async def handle_teamkill_report(self, gametime, reporter_id, reporter_name, teamkiller_id, teamkiller_name):
        """
            Sent when a player is teamkilled and clicks the 'Report' button.

            :param gametime: seconds of gametime when kill happened
            :param reporter_id: reporter id
            :param reporter_name: reporter nickname (for debug purpose only)
            :param teamkiller_id: teamkiller id
            :param teamkiller_name: teamkiller nickname (for debug purpose only)
        """

        pass

    async def handle_teamkill_happened(self, gametime, victim_id, victim_name, teamkiller_id, teamkiller_name):
        """
            Send automatically by the game whenever a teamkill happens. Takes
            the same parameters as TeamkillReport.

            :param gametime: seconds of gametime when kill happened
            :param victim_id: victim id
            :param victim_name: victim nickname (for debug purpose only)
            :param teamkiller_id: teamkiller id
            :param teamkiller_name: teamkiller nickname (for debug purpose only)
        """
        victim_id = int(victim_id)
        teamkiller_id = int(teamkiller_id)

        if 0 in (victim_id, teamkiller_id):
            self._logger.debug("Ignoring teamkill for AI player")
            return

        async with self._db.acquire() as conn:
            await conn.execute(
                teamkills.insert().values(
                    teamkiller=teamkiller_id,
                    victim=victim_id,
                    game_id=self.game.id,
                    gametime=gametime,
                )
            )

    async def handle_ice_message(self, receiver_id, ice_msg):
        receiver_id = int(receiver_id)
        peer = self.player_service.get_player(receiver_id)
        if not peer:
            self._logger.debug(
                "Ignoring ICE message for unknown player: %s", receiver_id
            )
            return

        game_connection = peer.game_connection
        if not game_connection:
            self._logger.debug(
                "Ignoring ICE message for player without game connection: %s", receiver_id
            )
            return

        try:
            await game_connection.send({
                "command": "IceMsg",
                "args": [int(self.player.id), ice_msg]
            })
        except DisconnectedError:
            self._logger.debug(
                "Failed to send ICE message to player due to a disconnect: %s",
                receiver_id
            )

    async def handle_game_state(self, state):
        """
        Changes in game state
        :param state: new state
        :return: None
        """

        try:
            # nasty hack work-around ICE adapter drops 2nd arg of GameState
            # we bunged the substate arg into a GameOptions message just before we sent GameState
            substate = self.player.own_game_substate

            if state == "Idle":
                await self._handle_idle_state()
                raise GameStateNotDirty

            elif state == "Lobby" and substate == "Staging":
                # TODO: Do we still need to schedule with `ensure_future`?
                #
                # We do not yield from the task, since we
                # need to keep processing other commands while it runs
                await self._handle_staging_state()

            elif state == "Lobby" and substate == "Battleroom":
                await self._handle_battleroom_state()

            elif state == "Launching" and substate == "Launching":
                await self._handle_launching_state()

            elif state == "Launching" and substate == "Live":
                await self._handle_live_state()

            elif state == "Ended":
                await self.on_connection_lost()

            self._mark_dirty()

        except GameStateNotDirty:
            pass

    async def handle_game_ended(self, *args):
        """
        Signals that the simulation has ended.
        """
        self.finished_sim = True
        await self.game.check_sim_end()

        # FIXME Move this into check_sim_end
        if self.game.ended:
            await self.game.on_game_end()

    async def handle_rehost(self, *args):
        """
        Signals that the user has rehosted the game. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_bottleneck(self, *args):
        """
        Not sure what this command means. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_bottleneck_cleared(self, *args):
        """
        Not sure what this command means. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_disconnected(self, *args):
        """
        Not sure what this command means. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_chat(self, message: str):
        """
        Whenever the player sends a chat message during the game lobby.
        """
        pass

    async def handle_game_full(self):
        """
        Sent when all game slots are full
        """
        pass

    def _mark_dirty(self, only_to_peers=False, pings_only=False):
        if self.game:
            self.game_service.mark_dirty(self.game, only_to_peers, pings_only)

    async def abort(self, log_message: str = ""):
        """
        Abort the connection

        Removes the GameConnection object from any associated Game object,
        and deletes references to Player and Game held by this object.
        """
        try:
            if self._state is GameConnectionState.ENDED:
                return

            self._logger.debug("%s.abort(%s)", self, log_message)

            if self.game.state in (GameState.STAGING, GameState.BATTLEROOM):
                await self.disconnect_all_peers()

            self._state = GameConnectionState.ENDED
            await self.game.remove_game_connection(self)
            self._mark_dirty()
            self.player_service.set_player_state(self.player, PlayerState.IDLE)
            if self.player.lobby_connection:
                self.player.lobby_connection.game_connection = None
            del self.player.game
            del self.player.game_connection
        except Exception as ex:  # pragma: no cover
            self._logger.debug("Exception in abort(): %s", ex)

    async def disconnect_all_peers(self):
        tasks = []
        for peer in self.game.connections:
            if peer == self:
                continue

            tasks.append(peer.send_DisconnectFromPeer(self.player.id))

        for fut in asyncio.as_completed(tasks):
            try:
                await fut
            except Exception:
                self._logger.debug(
                    "peer_sendDisconnectFromPeer failed for player %i",
                    self.player.id,
                    exc_info=True
                )

    async def on_connection_lost(self):
        try:
            await self.game.remove_game_connection(self)
        except Exception as e:  # pragma: no cover
            self._logger.exception(e)
        finally:
            await self.abort()

    def __str__(self):
        return "GameConnection({}, {})".format(self.player, self.game)


COMMAND_HANDLERS = {
    "Desync":               GameConnection.handle_desync,
    "GameState":            GameConnection.handle_game_state,
    "GameOption":           GameConnection.handle_game_option,
    "GameMods":             GameConnection.handle_game_mods,
    "PlayerOption":         GameConnection.handle_player_option,
    "AIOption":             GameConnection.handle_ai_option,
    "ClearSlot":            GameConnection.handle_clear_slot,
    "GameResult":           GameConnection.handle_game_result,
    "OperationComplete":    GameConnection.handle_operation_complete,
    "JsonStats":            GameConnection.handle_json_stats,
    "EnforceRating":        GameConnection.handle_enforce_rating,
    "TeamkillReport":       GameConnection.handle_teamkill_report,
    "TeamkillHappened":     GameConnection.handle_teamkill_happened,
    "GameEnded":            GameConnection.handle_game_ended,
    "Rehost":               GameConnection.handle_rehost,
    "Bottleneck":           GameConnection.handle_bottleneck,
    "BottleneckCleared":    GameConnection.handle_bottleneck_cleared,
    "Disconnected":         GameConnection.handle_disconnected,
    "IceMsg":               GameConnection.handle_ice_message,
    "Chat":                 GameConnection.handle_chat,
    "GameFull":             GameConnection.handle_game_full,
    "GameMetrics":          GameConnection.handle_game_metrics
}
