import asyncio
from typing import Optional
from irctokens import build, Line
from ircrobots import Bot as BaseBot, Server as BaseServer, ConnectionParams, SASLUserPass
from server.config import config
from server.core import Service
from server.decorators import with_logger

class ConnectionError(Exception):
    pass

class IRCBot(BaseBot):
    """Main bot class that creates server instances"""
    def __init__(self, service: 'IrcService'):
        super().__init__()
        self.service = service
        self._server = None  # Will hold our IRCServer instance

    def create_server(self, name: str):
        """Factory method to create server instances"""
        self._server = IRCServer(self, name, self.service)
        return self._server

@with_logger
class IRCServer(BaseServer):
    """Handles the actual IRC protocol interaction"""
    def __init__(self, bot: BaseBot, name: str, service: 'IrcService'):
        super().__init__(bot, name)
        self.service = service

    async def line_read(self, line: Line):
        """Called when a line is received from the server"""
        self.service._logger.debug("<- %s", line.format())

        if line.command == "001":
            self.service._logger.info("Connected to IRC server")
            if config.IRC_OPER_NAME and config.IRC_OPER_PASS:
                await self.send(build("OPER", [config.IRC_OPER_NAME, config.IRC_OPER_PASS]))
            self.service._on_connected()  # Notify service we're connected

        if line.command == "ERROR" and "Closing Link" in line.params[0]:
            raise ConnectionError(line.params[0])

    async def line_send(self, line: Line):
        """Called when a line is sent to the server"""
        self.service._logger.debug("-> %s", line.format().replace(config.IRC_PASS, "<ircpass>").replace(config.IRC_OPER_PASS, "<operpass>"))

@with_logger
class IrcService(Service):
    """
    IRC service with persistent connection and command queue processing.
    """
    def __init__(self):
        self._bot: Optional[IRCBot] = None
        self._accept_input = False
        self._command_queue = asyncio.Queue()
        self._main_task: Optional[asyncio.Task] = None
        self._queue_task: Optional[asyncio.Task] = None
        self._is_connected = False

    async def initialize(self) -> None:
        """Start the IRC connection loop and queue processor."""
        self._accept_input = True
        self._main_task = asyncio.create_task(self._run_bot())
        self._queue_task = asyncio.create_task(self._process_queue())
        self._logger.info("IrcService started")

    def _on_connected(self):
        """Called when IRC connection is established"""
        self._is_connected = True
        self._logger.debug("IRC connection established, queue processing active")

    def _on_disconnected(self):
        """Called when IRC connection is lost"""
        self._is_connected = False
        self._logger.debug("IRC connection lost, queue processing paused")

    async def _process_queue(self):
        """Continuously process the command queue when connected"""
        while self._accept_input:
            try:
                if self._is_connected and self._bot and self._bot._server:
                    cmd = await self._command_queue.get()
                    self._logger.debug("Processing queued command: %s", cmd)
                    await self._bot._server.send_raw(cmd)
                    self._command_queue.task_done()
                else:
                    await asyncio.sleep(1)  # Wait before checking connection again
            except Exception as e:
                self._logger.error("Queue processing error: %s", e)
                await asyncio.sleep(1)

    async def _run_bot(self):
        """Run the IRC bot with reconnection logic."""
        backoff = config.IRC_RECONNECT_DELAY
        while self._accept_input:
            try:
                self._bot = IRCBot(self)
                params = ConnectionParams.from_hoststring(config.IRC_NICK, config.IRC_HOSTSTRING)
                params.sasl = SASLUserPass(config.IRC_NICK, config.IRC_PASS) if config.IRC_PASS else None
                params.reconnect = config.IRC_RECONNECT_DELAY

                await self._bot.add_server("irc_server", params)
                await self._bot.run()
            except ConnectionError as e:
                self._logger.error("IRC connection error: %s", e)
                self._on_disconnected()
            except Exception as e:
                self._logger.exception("Unexpected IRC error:")
                self._on_disconnected()
            finally:
                if self._accept_input:
                    self._logger.info("Reconnecting in %d seconds...", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                if self._bot:
                    await self._bot.shutdown()
                    self._bot = None
                    self._on_disconnected()

    async def enqueue(self, command: str):
        """Queue an IRC command to be sent."""
        if not self._accept_input:
            self._logger.warning("Dropped IRC command (service shutting down): %s", command)
            return

        self._logger.debug("Enqueuing command: %s", command)
        await self._command_queue.put(command)

    async def shutdown(self):
        """Clean shutdown of the service."""
        self._accept_input = False
        if self._bot:
            await self._bot.shutdown()
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        if self._queue_task:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
        self._logger.info("IrcService shut down cleanly")

    # === High-level ban helpers ===
    async def add_chat_ban(self, mask: str, duration: str, reason: str):
        command = config.IRC_ADD_CHAT_BAN.format(mask=mask, duration=duration, reason=reason)
        await self.enqueue(command)

    async def del_chat_ban(self, mask: str):
        command = config.IRC_DEL_CHAT_BAN.format(mask=mask)
        await self.enqueue(command)

    async def add_channel_ban(self, mask: str, duration: str, reason: str):
        command = config.IRC_ADD_CHANNEL_BAN.format(mask=mask, duration=duration, reason=reason)
        await self.enqueue(command)

    async def del_channel_ban(self, mask: str):
        command = config.IRC_DEL_CHANNEL_BAN.format(mask=mask)
        await self.enqueue(command)
