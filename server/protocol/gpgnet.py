from abc import ABCMeta, abstractmethod
from typing import List, Union, Optional


class GpgNetServerProtocol(metaclass=ABCMeta):
    """
    Defines an interface for the server side GPGNet protocol
    """
    async def send_ConnectToPeer(self, address: Optional[str], player_name: str, player_uid: int, offer: bool):
        """
        Tells a client that has a listening LobbyComm instance to connect to the given peer
        :param address: ';' separated list of addresses to try, or None.
                        Ignored (and dropped) by ICE adapter when forwarding to game.
                        If present, we'll tac it onto end of player name so it doesn't get lost if theres an ICE adapter in the way.
        :param player_name: Remote player name
        :param player_uid: Remote player identifier
        """
        if False:
            player_name_and_address = "{}@{}".format(player_name, address)
            await self.send_gpgnet_message("ConnectToPeer", [player_name_and_address, player_uid, offer])
        else:
            await self.send_gpgnet_message("ConnectToPeer", [player_name, player_uid, offer])

    async def send_JoinGame(self, address: Optional[str], remote_player_name: str, remote_player_uid: int):
        """
        Tells the game to join the given peer by ID
        :param address: ';' separated list of addresses to try, or None.
                        Ignored (and dropped) by ICE adapter when forwarding to game.
                        If present, we'll tac it onto end of player name so it doesn't get lost if theres an ICE adapter in the way.
        :param remote_player_name:
        :param remote_player_uid:
        """
        if False:
            remote_player_name_and_address = "{}@{}".format(remote_player_name, address)
            await self.send_gpgnet_message("JoinGame", [remote_player_name_and_address, remote_player_uid])
        else:
            await self.send_gpgnet_message("JoinGame", [remote_player_name, remote_player_uid])

    async def send_HostGame(self, map_path):
        """
        Tells the game to start listening for incoming connections as a host
        :param map_path: Which scenario to use
        """
        await self.send_gpgnet_message("HostGame", [str(map_path)])

    async def send_DisconnectFromPeer(self, id: int):
        """
        Instructs the game to disconnect from the peer given by id

        :param id:
        :return:
        """
        await self.send_gpgnet_message("DisconnectFromPeer", [id])

    async def send_gpgnet_message(self, command_id: str, arguments: List[Union[int, str, bool]]):
        message = {"command": command_id, "args": arguments}
        await self.send(message)

    @abstractmethod
    async def send(self, message):
        pass  # pragma: no cover


class GpgNetClientProtocol(metaclass=ABCMeta):
    def send_GameState(self, arguments: List[Union[int, str, bool]]) -> None:
        """
        Sent by the client when the state of LobbyComm changes
        """
        self.send_gpgnet_message("GameState", arguments)

    @abstractmethod
    def send_gpgnet_message(self, command_id, arguments: List[Union[int, str, bool]]) -> None:
        pass  # pragma: no cover
