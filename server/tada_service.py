import asyncio
from typing import Set, Dict, Union, List, Any

import aiocron
import aiohttp
import datetime
import lxml.html
import os
import shutil
import sqlalchemy.sql

from server.decorators import with_logger
from .config import config
from .core import Service
from .db import FAFDatabase


class TadaFileTooLargeException(ValueError):

    def __init__(self, file_size_mb, max_size_mb):
        self.file_size_mb = file_size_mb
        self.max_size_mb = max_size_mb


class TadaUploadFailException(ValueError):

    def __init__(self, reason):
        self.reason = reason


@with_logger
class TadaService(Service):
    def __init__(self, database: FAFDatabase):
        """
        :param tada_endpoint: eg  'https://tademos.xyz'
        """
        self._db = database
        tada_api_url = config.TADA_API_URL
        self._upload_endpoint = f'{tada_api_url}/demos'
        self._games_endpoint = f'{tada_api_url}/demos'
        self._dirty_uploads = []
        self._upload_queue = []

    @property
    def dirty_uploads(self):
        return self._dirty_uploads

    def clear_dirty(self):
        self._dirty_uploads = []

    def mark_dirty(self, taf_id: int, tada_game_info: Dict[str, Union[List[Dict[str, Any]], Any]]):
        self._dirty_uploads.append((taf_id, tada_game_info))

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
            if retry_count <= 0 or isinstance(e, TadaFileTooLargeException):
                self._logger.exception(e)
                self._logger.info("[upload] giving up. restoring game_stats.tada_available=0")
                async with self._db.acquire() as conn:
                    await conn.execute(sqlalchemy.sql.text(
                        "UPDATE `game_stats` SET `tada_available`=0 WHERE id = :taf_replay_id"),
                        taf_replay_id=taf_replay_id)
                raise e

            else:
                self._logger.info(f"[upload] Exception uploading replay:{str(e)}. retry_count:{retry_count}")
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
            datestamp = datetime.date.fromtimestamp(os.path.getctime(zip_or_tad_file_path)).isoformat()
            if replay_meta is None:
                canonical_file_name = "{datestamp} - TAF-{replay_id}.tad".format(
                    datestamp=datestamp,
                    replay_id=taf_replay_id)
            else:
                canonical_file_name = "{datestamp} - {map_name} - {player_list}.{extension}".format(
                    datestamp=replay_meta["datestamp"],
                    map_name=replay_meta["mapName"],
                    player_list=", ".join([p["name"] for p in replay_meta["players"]]),
                    extension=replay_meta["file_extension"])
            self._logger.info(f"[_upload] canonical_file_name={canonical_file_name}")

            recent_tada_games = await self._get_latest_games()
            recent_tada_id, _ = recent_tada_games[-1] if len(recent_tada_games) > 0 else 0

            tad_file_size_mb = os.path.getsize(tad_file_path) // 1024 // 1024
            if tad_file_size_mb >= config.TADA_UPLOAD_MAX_SIZE_MB:
                self._logger.info("[_upload] skipping actual upload to TADA because file size {}MB exceed maximum {}MB".format(
                    tad_file_size_mb, config.TADA_UPLOAD_MAX_SIZE_MB))
                raise TadaFileTooLargeException(tad_file_size_mb, config.TADA_UPLOAD_MAX_SIZE_MB)

            elif not config.TADA_UPLOAD_ENABLE:
                self._logger.info("[_upload] skipping actual upload to TADA because config.TADA_UPLOAD_ENABLE not set")

            else:
                await self._do_upload(tad_file_path, canonical_file_name)

            tada_game_info, map_name, players = None, None, None
            if replay_meta is not None:
                map_name = replay_meta["mapName"]
                players = set(p["name"] for p in replay_meta["players"] if p["side"] < 2)

            for n in range(3):
                await asyncio.sleep(5)
                latest_games = await self._get_latest_games()
                tada_game_info = self._find_tada_game(latest_games, 1+recent_tada_id, datestamp, map_name, players)
                if tada_game_info is not None:
                    tada_id, tada_game_info = tada_game_info
                    self._logger.info(f"game successfully uploaded. id={tada_id}")
                    self.mark_dirty(taf_replay_id, tada_game_info)
                    break

            if tada_game_info is None:
                self._logger.info(f"Unable to find uploaded game in TADA list of latest uploads")

        finally:
            cleanup()

    def _find_tada_game(self, tada_games, min_id: int, datestamp: str, map_name: str, players: Set[str]):

        def match(game_name: str, map_name: str, players: Set[str]):
            if map_name is not None and map_name not in game_name:
                return False
            if players is not None:
                for player in players:
                    if player not in game_name:
                        return False
            return True

        self._logger.info(f"_find_tada_game: min_id={min_id}, map_name={map_name}, players={players}")
        for id, name in tada_games:
            if id >= min_id and match(name, map_name, players) or not config.TADA_UPLOAD_ENABLE:
                tada_game_info = name.split(" - ")
                if len(tada_game_info) == 3:
                    tada_game_info = {
                        "party": id,
                        "mapName": tada_game_info[1],
                        "date": tada_game_info[0],
                        "players": [{"name": p, "side": "ARM"} for p in tada_game_info[2].split(", ")]
                    }
                else:
                    tada_game_info = {
                        "party": id,
                        "mapName": map_name,
                        "date": datestamp,
                        "players": [{"name": p, "side": "ARM"} for p in players]
                    }
                return id, tada_game_info

    async def _do_upload(self, tad_file_path: str, upload_name: str) -> str:
        with open(tad_file_path, "rb") as f:
            async with aiohttp.ClientSession(headers={"User-Agent": "Total Annihilation Forever"}) as session:
                self._logger.info(f"uploading file={tad_file_path} to endpoint={self._upload_endpoint}")
                data = aiohttp.FormData()
                data.add_field("demo[recording]", f, filename=upload_name, content_type='multipart/form-data')
                async with session.post(self._upload_endpoint, data=data, verify_ssl=False) as r:
                    if r.status != 200:
                        raise TadaUploadFailException(r.reason)

    async def _get_latest_games(self):
        """
        :return: list of most recent (id, name) sorted ascending by id
        """
        class AccumulateGames(object):

            def __init__(self):
                self.id = None
                self.games_list = []

            def get(self):
                return self.games_list

            def start(self, tag, attrib):
                self.id = None
                if tag == 'a' and attrib['href'].startswith('/demos/'):
                    try:
                        self.id = int(attrib['href'].split('/')[2])
                    except ValueError:
                        pass

            def end(self, tag):
                pass

            def data(self, data):
                if self.id is not None:
                    self.games_list += [[self.id, data]]

            def comment(self, text):
                pass

            def close(self):
                self.games_list.sort(key=lambda x: x[0])
                return "closed!"

        async with aiohttp.ClientSession() as session:
            async with session.get(self._games_endpoint, verify_ssl=False) as r:
                if r.status != 200:
                    raise ValueError(f"Got {r.status} from TADA endpoint!")
                games = await r.text()

        games_accumulator = AccumulateGames()
        parser = lxml.html.HTMLParser(target = games_accumulator)
        lxml.html.fromstring(games, None, parser)
        return games_accumulator.get()

