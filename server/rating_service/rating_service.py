import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Callable, Coroutine, Awaitable, List, Set

import aiocron
from sqlalchemy import and_, case, func, select
from trueskill import Rating

from server.config import config
from server.core import Service
from server.db import FAFDatabase
from server.db.models import (
    game_player_stats,
    leaderboard,
    leaderboard_rating,
    leaderboard_rating_journal
)
from server.decorators import with_logger
from server.games.game_results import GameOutcome
from server.metrics import rating_service_backlog
from server.player_service import PlayerService
from server.rating import RatingTypeMap

from .game_rater import GameRater, GameRatingError
from .typedefs import (
    PlayerID,
    ServiceNotReadyError, RankedRating, TeamID,
)
from ..games.typedefs import EndedGameInfo, OutcomeLikelihoods


@asynccontextmanager
async def acquire_or_default(db, default=None):
    if default is None:
        async with db.acquire() as conn:
            yield conn
    else:
        yield default


@with_logger
class RatingService(Service):
    """
    Service responsible for calculating and saving trueskill rating updates.
    To avoid race conditions, rating updates from a single game ought to be
    atomic.
    """

    def __init__(self, database: FAFDatabase, player_service: PlayerService):
        self._db = database
        self._on_player_rating_change = player_service.on_player_rating_change
        self._accept_input = False
        self._queue = asyncio.Queue()
        self._task = None
        self._rating_type_ids = None
        self._game_rating_callbacks = []

    def add_game_rating_callback(self, callback: Callable[[EndedGameInfo,
                                                           Dict[PlayerID, RankedRating],        # old_ratings
                                                           Dict[PlayerID, Rating],              # new_ratings
                                                           Dict[TeamID, OutcomeLikelihoods]     # likelihood of outcome
                                                           ], Awaitable[None]]) -> None:
        self._game_rating_callbacks += [callback]

    async def initialize(self) -> None:
        if self._task is not None:
            self._logger.error("Service already runnning or not properly shut down.")
            return

        await self.update_data()
        self._update_cron = aiocron.crontab("*/10 * * * *", func=self.update_data)
        self._accept_input = True
        self._logger.debug("RatingService starting...")
        self._task = asyncio.create_task(self._handle_rating_queue())

    async def update_data(self):
        async with self._db.acquire() as conn:

            initializer = leaderboard.alias()
            sql = select(
                leaderboard.c.id,
                leaderboard.c.technical_name,
                initializer.c.technical_name.label("initializer")
            ).select_from(
                leaderboard.outerjoin(
                    initializer,
                    leaderboard.c.initializer_id == initializer.c.id
                )
            )
            result = await conn.execute(sql)
            rows = result.fetchall()

        self._rating_type_ids = RatingTypeMap(
            None,
            ((row.technical_name, row.id) for row in rows)
        )

    async def enqueue(self, game_info: EndedGameInfo) -> None:
        if not self._accept_input:
            self._logger.warning("Dropped rating request %s", game_info)
            raise ServiceNotReadyError(
                "RatingService not yet initialized or shutting down."
            )

        self._logger.debug("Queued up rating request %s", game_info)
        await self._queue.put(game_info)
        rating_service_backlog.set(self._queue.qsize())

    async def _handle_rating_queue(self) -> None:
        self._logger.debug("RatingService started!")
        try:
            while self._accept_input or not self._queue.empty():
                game_info = await self._queue.get()
                self._logger.debug("Now rating request %s", game_info)

                try:
                    await self._rate(game_info)
                except GameRatingError:
                    self._logger.warning("Error rating game %s", game_info)
                except Exception:  # pragma: no cover
                    self._logger.exception("Failed rating request %s", game_info)
                else:
                    self._logger.debug("Done rating request.")

                self._queue.task_done()
                rating_service_backlog.set(self._queue.qsize())
        except asyncio.CancelledError:
            pass
        except Exception:
            self._logger.critical(
                "Unexpected exception while handling rating queue.",
                exc_info=True
            )

        self._logger.debug("RatingService stopped.")

    async def _rate(self, game_info: EndedGameInfo) -> None:
        player_id_set = set([player_info.player_id for player_info in game_info.ended_game_player_summary])
        _old_ratings: Dict[PlayerID, RankedRating] = await self._get_player_ratings(player_id_set, game_info.rating_type)
        old_ratings: Dict[PlayerID, Rating] = {pid: r.rating for pid, r in _old_ratings.items()}
        new_ratings, team_outcome_likelihoods = GameRater.compute_rating(game_info.ended_game_player_summary, old_ratings)

        for f in self._game_rating_callbacks:
            await f(game_info, _old_ratings, new_ratings, team_outcome_likelihoods)

        await self._persist_rating_changes(game_info, old_ratings, new_ratings)

    async def _get_player_ratings(self, player_ids: Set[int], rating_type: str, conn=None) -> Dict[PlayerID, RankedRating]:
        if self._rating_type_ids is None:
            self._logger.warning(
                "Tried to fetch player data before initializing service."
            )
            raise ServiceNotReadyError("RatingService not yet initialized.")

        rating_type_id = self._rating_type_ids.get(rating_type)
        if rating_type_id is None:
            raise ValueError(f"Unknown rating type {rating_type}.")

        async with acquire_or_default(self._db, conn) as conn:
            sql = select(
                leaderboard_rating.c.login_id, leaderboard_rating.c.mean, leaderboard_rating.c.deviation, leaderboard_rating.c.rating
            ).where(leaderboard_rating.c.leaderboard_id == rating_type_id)
            result = await conn.execute(sql)
            rows = result.fetchall()

            ratings = [(row.login_id, row.mean, row.deviation, row.rating) for row in rows]
            retrieved_player_ids = set([row.login_id for row in rows])
            for pid in player_ids:
                if pid not in retrieved_player_ids:
                    new_rating = await self._create_default_rating(conn, pid, rating_type)
                    ratings += [(pid, new_rating.mu, new_rating.sigma, new_rating.mu-3.*new_rating.sigma)]

        sorted_ratings = sorted(ratings, key=lambda x: x[3], reverse=True)
        return {r[0]: RankedRating(r[1], r[2], rank, len(sorted_ratings))
                for rank, r in enumerate(sorted_ratings)
                if r[0] in player_ids}

    async def _create_default_rating(
        self, conn, player_id: int, rating_type: str
    ):
        default_mean = config.START_RATING_MEAN
        default_deviation = config.START_RATING_DEV
        rating_type_id = self._rating_type_ids.get(rating_type)

        insertion_sql = leaderboard_rating.insert().values(
            login_id=player_id,
            mean=default_mean,
            deviation=default_deviation,
            total_games=0,
            won_games=0,
            lost_games=0,
            drawn_games=0,
            streak=0,
            best_streak=0,
            recent_scores="",
            leaderboard_id=rating_type_id,
        )
        await conn.execute(insertion_sql)

        return Rating(default_mean, default_deviation)

    async def _persist_rating_changes(
        self,
        game_info: EndedGameInfo,
        old_ratings: Dict[PlayerID, Rating],
        new_ratings: Dict[PlayerID, Rating]
    ) -> None:
        """
        Persist computed ratings to the respective players' selected rating
        """
        self._logger.debug("Saving rating change stats for game %i", game_info.game_id)

        async with self._db.acquire() as conn:
            for player_info in game_info.ended_game_player_summary:
                old_rating = old_ratings[player_info.player_id]
                new_rating = new_ratings[player_info.player_id]
                self._logger.debug(
                    "New %s rating for player with id %s: %s -> %s",
                    game_info.rating_type,
                    player_info.player_id,
                    old_rating,
                    new_rating,
                )

                gps_update_sql = (
                    game_player_stats.update()
                    .where(
                        and_(
                            game_player_stats.c.playerId == player_info.player_id,
                            game_player_stats.c.gameId == game_info.game_id,
                        )
                    )
                    .values(
                        after_mean=new_rating.mu,
                        after_deviation=new_rating.sigma,
                        mean=old_rating.mu,
                        deviation=old_rating.sigma,
                        scoreTime=func.now(),
                    )
                )
                result = await conn.execute(gps_update_sql)

                if not result.rowcount:
                    self._logger.warning("gps_update_sql resultset is empty for game_id %i", game_info.game_id)
                    return

                rating_type_id = self._rating_type_ids[game_info.rating_type]

                journal_insert_sql = leaderboard_rating_journal.insert().values(
                    leaderboard_id=rating_type_id,
                    rating_mean_before=old_rating.mu,
                    rating_deviation_before=old_rating.sigma,
                    rating_mean_after=new_rating.mu,
                    rating_deviation_after=new_rating.sigma,
                    game_player_stats_id=select(game_player_stats.c.id).where(
                        and_(
                            game_player_stats.c.playerId == player_info.player_id,
                            game_player_stats.c.gameId == game_info.game_id,
                        )
                    ).scalar_subquery(),
                )
                await conn.execute(journal_insert_sql)

                victory_increment = (
                    1 if player_info.outcome is GameOutcome.VICTORY else 0
                )
                draw_increment = (
                    1 if player_info.outcome is GameOutcome.DRAW else 0
                )
                defeat_increment = (
                    1 if player_info.outcome is GameOutcome.DEFEAT else 0
                )
                score = (
                    1 if player_info.outcome is GameOutcome.VICTORY else
                    0 if player_info.outcome is GameOutcome.DRAW else
                    -1)
                rating_update_sql = (
                    leaderboard_rating.update()
                    .where(
                        and_(
                            leaderboard_rating.c.login_id == player_info.player_id,
                            leaderboard_rating.c.leaderboard_id == rating_type_id,
                        )
                    )
                    .values(
                        mean=new_rating.mu,
                        deviation=new_rating.sigma,
                        total_games=leaderboard_rating.c.total_games + 1,
                        won_games=leaderboard_rating.c.won_games + victory_increment,
                        drawn_games=leaderboard_rating.c.drawn_games + draw_increment,
                        lost_games=leaderboard_rating.c.lost_games + defeat_increment,
                        streak=case((leaderboard_rating.c.streak * score >= 0, leaderboard_rating.c.streak + score), else_ = score),
                        best_streak=case((leaderboard_rating.c.streak > leaderboard_rating.c.best_streak, leaderboard_rating.c.streak), else_=leaderboard_rating.c.best_streak),
                        recent_scores=func.substr(func.concat(str(score+1), leaderboard_rating.c.recent_scores), 1, 10),
                        recent_mod=game_info.game_mode
                    )
                )
                await conn.execute(rating_update_sql)

                self._on_player_rating_change(
                    player_info.player_id, game_info.rating_type, new_ratings[player_info.player_id])

    async def _join_rating_queue(self) -> None:
            """
            Offers a call that is blocking until the rating queue has been emptied.
            Mostly for testing purposes.
            """
            await self._queue.join()

    async def shutdown(self) -> None:
        """
        Finish rating all remaining games, then exit.
        """
        self._accept_input = False
        self._logger.debug(
            "Shutdown initiated. Waiting on current queue: %s", self._queue
        )
        await self._queue.join()
        self._task = None
        self._logger.debug("Queue emptied: %s", self._queue)

    def kill(self) -> None:
        """
        Exit without waiting for the queue to join.
        """
        self._accept_input = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
