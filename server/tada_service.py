import asyncio
from typing import Set

import aiocron
import aiohttp
import datetime
import os
import shutil
import sqlalchemy.sql

from server.decorators import with_logger
from .config import config
from .core import Service
from .db import FAFDatabase

@with_logger
class TadaService(Service):
    def __init__(self, database: FAFDatabase):
        """
        :param tada_endpoint: eg  'https://z151e60yl7.execute-api.us-east-2.amazonaws.com'
        """
        self._db = database
        tada_api_url = config.TADA_API_URL
        self._upload_endpoint = f'{tada_api_url}/staging/upload'
        self._games_endpoint = f'{tada_api_url}/staging/games'
        self._dirty_uploads = []
        self._upload_queue = []

    @property
    def dirty_uploads(self):
        return self._dirty_uploads

    def clear_dirty(self):
        self._dirty_uploads = []

    def mark_dirty(self, taf_id: int, tada_id: str):
        self._dirty_uploads.append((taf_id, tada_id))

    async def initialize(self) -> None:
        self._upload_cron = aiocron.crontab("* * * * *", func=self._service_queue)

    async def shutdown(self):
        pass

    def on_connection_lost(self, conn: "LobbyConnection") -> None:
        pass

    async def upload(self, taf_replay_id: int, replay_meta: dict, zip_or_tad_file_path: str, retry_count: int):
        try:
            await self._upload(taf_replay_id, replay_meta, zip_or_tad_file_path)

        except Exception as e:
            if retry_count <= 0:
                self._logger.exception(e)
                self._logger.info("giving up. restoring game_stats.tada_available=0")
                async with self._db.acquire() as conn:
                    await conn.execute(sqlalchemy.sql.text(
                        "UPDATE `game_stats` SET `tada_available`=0 WHERE id = :taf_replay_id"),
                        taf_replay_id=taf_replay_id)

            else:
                self._logger.info(f"Exception uploading replay:{str(e)}. retry_count:{retry_count}")
                self._upload_queue.append((taf_replay_id, replay_meta, zip_or_tad_file_path, retry_count-1))

    async def _service_queue(self):
        queue_items, self._upload_queue = self._upload_queue, []
        for args in queue_items:
            await self.upload(*args)

    async def _upload(self, taf_replay_id: int, replay_meta: dict, zip_or_tad_file_path: str):
        if zip_or_tad_file_path.endswith(".zip"):
            tad_file_path = os.path.splitext(zip_or_tad_file_path)[0] + ".tad"
            def cleanup(): os.remove(tad_file_path)
            shutil.unpack_archive(zip_or_tad_file_path, os.path.dirname(zip_or_tad_file_path) or './')

        else:
            def cleanup(): pass
            tad_file_path = zip_or_tad_file_path

        try:
            if config.TADA_UPLOAD_ENABLE:
                await self._do_upload(tad_file_path)
            else:
                self._logger.info("skipping actual upload to TADA because config.TADA_UPLOAD_ENABLE not set")

            upload_time = datetime.datetime.utcnow()

            tada_game_info, map_name, players = None, None, None
            if replay_meta is not None:
                map_name = replay_meta["mapName"]
                players = set(p["name"] for p in replay_meta["players"])
            for n in range(3):
                await asyncio.sleep(5)
                latest_games = await self._get_latest_games()
                tada_game_info = self._find_tada_game(latest_games, upload_time, map_name, players)
                if tada_game_info is not None:
                    tada_game_id = tada_game_info["party"]
                    self._logger.info(f"game successfully uploaded. id={tada_game_id}")
                    self.mark_dirty(taf_replay_id, tada_game_info)
                    break

            if tada_game_info is None:
                self._logger.info(f"Unable to find uploaded game in TADA list of latest uploads")

        finally:
            cleanup()

    def _find_tada_game(self, tada_games, upload_time: datetime.datetime, map_name: str, players: Set[str]):
        self._logger.info(f"_find_tada_game: upload_time={upload_time}, map_name={map_name}, players={players}")
        for game in tada_games:
            tada_upload_time = game["uploaded"].split(".")[0]+"Z"
            tada_upload_time = datetime.datetime.strptime(tada_upload_time, "%Y-%m-%dT%H:%M:%SZ")
            tada_map = game["mapName"]
            tada_players = set(p["name"] for p in game["players"])
            if abs(upload_time-tada_upload_time) < datetime.timedelta(seconds=10) and \
                    (map_name is None or map_name == tada_map) and \
                    (players is None or players == tada_players):
                self._logger.info("uploaded game found")
                return game

    async def _do_upload(self, tad_file_path: str) -> str:
        async with aiohttp.ClientSession() as session:
            self._logger.info(f"retrieving signed url for upload to TADA")
            async with session.get(self._upload_endpoint, verify_ssl=False) as r:
                if r.status != 200:
                    raise ValueError("Unable to get signed url")

                signed_url = await r.json()
                signed_url = signed_url["signedUrl"]

            self._logger.info(f"uploading file={tad_file_path} to signed_url={signed_url}")
            with open(tad_file_path, "rb") as f:
                async with session.put(signed_url, data=f) as r:
                    if r.status != 200:
                        raise ValueError("Unable to upload replay to TADA")

        self._logger.info(f"upload completed")

    async def _get_latest_games(self):
        async with aiohttp.ClientSession() as session:
            self._logger.info(f"retrieving latest games")
            async with session.get(f"{self._games_endpoint}?order=Uploaded", verify_ssl=False) as r:
                if r.status != 200:
                    raise ValueError(f"Got {r.status} from TADA endpoign!")
                games = await r.json()
        return games['games']

