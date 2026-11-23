"""海龟汤的会话状态：数据库持久化、提问流程、提示与结算。

一局游戏同时存在于内存（``games``）与数据库（``TurtleSoupGame``）：

- 内存里保留谜题、历史与一把 ``asyncio.Lock``，串行处理同一会话的并发提问；
- 数据库里的记录用于跨重启恢复（默认作答期限 36 小时，远超一次进程的生命周期）；
- 过期由每分钟一次的清理任务静默处理：删除记录、恢复 Chat 回复，不发任何提示。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from . import chat_bridge, wallet
from .config import config
from .judge import generate_puzzle, judge_question, recalculate_progress
from .models import TurtleSoupGame, TurtleSoupPlayer
from .types import AskOutcome, EndOutcome, HintOutcome, HistoryItem, Puzzle

if TYPE_CHECKING:
    from nonebot.adapters import Bot, Event

# 会话 ID -> 进行中的一局
games: dict[str, "Game"] = {}


class GameError(RuntimeError):
    """本局无法继续（已过期、已结束或达到提问上限）。"""


class GameAlreadyPlayingError(GameError):
    pass


class QuestionLimitError(GameError):
    pass


class GameExpiredError(GameError):
    pass


@dataclass(slots=True)
class Game:  # pylint: disable=too-many-instance-attributes
    """一个会话内的一局海龟汤。"""

    row_id: int
    session_id: str
    owner_id: str
    puzzle: Puzzle
    history: list[HistoryItem]
    percent: int
    asked: int
    hint_index: int
    start_time: datetime
    expire_time: datetime
    finished: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def max_questions(self) -> int:
        return max(1, config.turtle_soup_max_questions)

    def deadline_left(self) -> float:
        return (self.expire_time - datetime.now()).total_seconds()

    def is_expired(self) -> bool:
        return self.deadline_left() <= 0

    def can_ask(self) -> bool:
        return self.asked < self.max_questions

    # ---------- 数据库 ----------

    def to_row(self) -> dict[str, object]:
        return {
            "puzzle_data": self.puzzle.model_dump_json(),
            "history_data": json.dumps([item.model_dump() for item in self.history], ensure_ascii=False),
            "percent": self.percent,
            "asked": self.asked,
            "hint_index": self.hint_index,
        }

    async def save(self) -> None:
        async with get_session() as session:
            row = await session.get(TurtleSoupGame, self.row_id)
            if row is None:
                # 记录被过期清理删除时不要静默当作保存成功
                raise GameExpiredError("本局记录已被清理")
            for key, value in self.to_row().items():
                setattr(row, key, value)
            await session.commit()

    async def delete_row(self) -> None:
        async with get_session() as session:
            await session.execute(delete(TurtleSoupGame).where(TurtleSoupGame.id_ == self.row_id))
            await session.commit()

    # ---------- 流程 ----------

    async def ask_question(
        self,
        user_id: str,
        question: str,
        bot: Optional[Bot] = None,
        event: Optional[Event] = None,
    ) -> AskOutcome:
        """判定一次提问；猜中时直接结算。"""
        question = question.strip()
        async with self.lock:
            self.ensure_alive()
            if not self.can_ask():
                raise QuestionLimitError("本局提问次数已用完")
            result = await judge_question(
                self.puzzle,
                self.history,
                self.percent,
                question,
                user_id,
                self.session_id,
            )
            self.ensure_alive()
            self.history.append(
                HistoryItem(
                    user_id=user_id,
                    question=question,
                    reply=result.reply,
                    percent=result.percent,
                ),
            )
            self.asked += 1
            self.percent = result.percent
            await self.save()
            outcome = AskOutcome(
                question=question,
                reply=result.reply,
                percent=self.percent,
                asked=self.asked,
                solved=result.solved,
                title=self.puzzle.title,
                puzzle_setting=self.puzzle.puzzle_setting,
                solution=self.puzzle.solution if result.solved else "",
                supplementary_info=self.puzzle.supplementary_info if result.solved else [],
            )
            if result.solved:
                end = await self.finish(solved=True, solved_by=user_id, bot=bot, event=event)
                outcome.reward = end.reward
            return outcome

    def ensure_alive(self) -> None:
        if self.finished:
            raise GameExpiredError("本局已经结束")
        if self.is_expired():
            raise GameExpiredError("本局已经过期")

    async def give_up(self, bot: Optional[Bot] = None, event: Optional[Event] = None) -> EndOutcome:
        """放弃本局并公布汤底。"""
        async with self.lock:
            self.ensure_alive()
            return await self.finish(solved=False, bot=bot, event=event)

    async def finish(
        self,
        *,
        solved: bool,
        solved_by: str = "",
        bot: Optional[Bot] = None,
        event: Optional[Event] = None,
    ) -> EndOutcome:
        """结束本局：投递事件、恢复 Chat、删除记录，解开时更新排行榜。"""
        if self.finished:
            raise GameExpiredError("本局已经结束")
        self.finished = True
        games.pop(self.session_id, None)
        if bot is not None and event is not None:
            try:
                await chat_bridge.publish_summary(
                    self.session_id,
                    bot,
                    event,
                    self.puzzle,
                    user_id=solved_by or self.owner_id,
                    solved=solved,
                )
                await chat_bridge.drain_session(self.session_id)
            except Exception:
                logger.opt(exception=True).warning("海龟汤：向 Chat 投递汤面与汤底失败")
            finally:
                chat_bridge.resume(self.session_id)
        else:
            chat_bridge.resume(self.session_id)
        try:
            await self.delete_row()
        except Exception:
            # 删除失败时记录留给过期清理任务处理，不要让结算消息发不出去
            logger.opt(exception=True).error(f"海龟汤：删除对局记录失败: {self.session_id}")
        if solved and solved_by:
            try:
                await record_correct(solved_by)
            except Exception:
                logger.opt(exception=True).error(f"海龟汤：更新正确作答数失败: {solved_by}")
            reward = await wallet.reward(solved_by, config.turtle_soup_reward)
        else:
            reward = 0.0
        return EndOutcome(
            solved=solved,
            percent=100 if solved else self.percent,
            asked=self.asked,
            title=self.puzzle.title,
            puzzle_setting=self.puzzle.puzzle_setting,
            solution=self.puzzle.solution,
            supplementary_info=self.puzzle.supplementary_info,
            solved_by=solved_by if solved else "",
            reward=reward,
        )

    async def next_hint(self, user_id: str) -> HintOutcome:
        """按顺序取出一条提示（附加信息），成功取到时向 ``user_id`` 收取提示费用。"""
        async with self.lock:
            self.ensure_alive()
            hints = self.puzzle.supplementary_info
            if not hints:
                return HintOutcome(finished=True, total=0)
            if self.hint_index >= len(hints):
                return HintOutcome(current=self.hint_index, total=len(hints), finished=True)
            # 没有提示可取时不收费：只有真的拿到提示才扣 VimCoin
            cost = config.turtle_soup_hint_cost
            await wallet.charge(user_id, cost)
            hint = hints[self.hint_index]
            self.hint_index += 1
            try:
                await self.save()
            except Exception:
                # 记录没写成时退回提示费用，避免收了钱却没给提示
                await wallet.refund(user_id, cost, "提示没能保存")
                raise
            return HintOutcome(
                hint=hint,
                current=self.hint_index,
                total=len(hints),
                finished=False,
                cost=cost,
            )

    async def recalculate(self, user_id: str) -> int:
        """依据完整历史重新计算进度（只增不减，最高 99）。"""
        async with self.lock:
            self.ensure_alive()
            self.percent = await recalculate_progress(
                self.puzzle,
                self.history,
                self.percent,
                user_id,
                self.session_id,
            )
            self.ensure_alive()
            await self.save()
            return self.percent


def _game_from_row(row: TurtleSoupGame) -> Game:
    return Game(
        row_id=row.id_,
        session_id=row.session_id,
        owner_id=row.owner_id,
        puzzle=Puzzle.model_validate_json(row.puzzle_data),
        history=_parse_history(row.history_data),
        percent=row.percent,
        asked=row.asked,
        hint_index=row.hint_index,
        start_time=row.start_time,
        expire_time=row.expire_time,
    )


def _parse_history(raw: str) -> list[HistoryItem]:
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        logger.warning("海龟汤：问答历史损坏，已重置")
        return []
    items: list[HistoryItem] = []
    for entry in data if isinstance(data, list) else []:
        try:
            items.append(HistoryItem.model_validate(entry))
        except Exception:
            logger.warning(f"海龟汤：跳过损坏的问答记录 {entry!r}")
    return items


# ---------- 对外查询 ----------


async def get_active_game(session_id: str) -> Optional[Game]:
    """取当前进行中的一局；已过期时静默清理并返回 None。"""
    game = games.get(session_id)
    if game is None:
        return None
    if game.is_expired():
        # 判定正在进行时不清理，让最后一条提问正常收尾；下一次清理任务再处理
        if not await _expire_game(game):
            return game
        return None
    return game


async def start_game(session_id: str, owner_id: str, theme: str = "") -> Game:
    """开始新的一局。

    先扣开局费用（``turtle_soup_generate_cost``，向发起者收取），再插入占位记录并生成谜题：
    ``session_id`` 上的唯一索引保证并发开局只有一个人能真正出题，另一个直接拿到
    :class:`GameAlreadyPlayingError`，不会白跑两次模型。开局没有成功（余额之外的一切失败）
    时费用原额退回，玩家不为一局没开起来的游戏付钱。
    """
    if await get_active_game(session_id) is not None:
        raise GameAlreadyPlayingError("当前会话已经有一局进行中的海龟汤")
    cost = config.turtle_soup_generate_cost
    await wallet.charge(owner_id, cost)
    try:
        return await _create_game(session_id, owner_id, theme)
    except Exception:
        await wallet.refund(owner_id, cost, "开局失败")
        raise


async def _create_game(session_id: str, owner_id: str, theme: str) -> Game:
    now = datetime.now()
    async with get_session() as session:
        row = TurtleSoupGame(
            session_id=session_id,
            owner_id=owner_id,
            puzzle_data="",
            history_data="[]",
            percent=0,
            asked=0,
            hint_index=0,
            start_time=now,
            expire_time=now + timedelta(seconds=max(1, config.turtle_soup_timeout)),
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise GameAlreadyPlayingError("当前会话已经有一局进行中的海龟汤") from e
        await session.refresh(row)
        row_id = row.id_
    try:
        puzzle = await generate_puzzle(theme)
    except Exception:
        # 出题失败时删掉占位记录，避免这个会话在 36 小时内都无法再开局
        try:
            async with get_session() as session:
                await session.execute(delete(TurtleSoupGame).where(TurtleSoupGame.id_ == row_id))
                await session.commit()
        except Exception:
            logger.opt(exception=True).warning(f"海龟汤：清理出题失败的占位记录失败: {session_id}")
        raise
    game = Game(
        row_id=row_id,
        session_id=session_id,
        owner_id=owner_id,
        puzzle=puzzle,
        history=[],
        percent=0,
        asked=0,
        hint_index=0,
        start_time=datetime.now(),
        expire_time=datetime.now() + timedelta(seconds=max(1, config.turtle_soup_timeout)),
    )
    async with get_session() as session:
        row = await session.get(TurtleSoupGame, row_id)
        if row is None:
            raise GameExpiredError("占位记录已被清理")
        row.puzzle_data = game.puzzle.model_dump_json()
        row.start_time = game.start_time
        row.expire_time = game.expire_time
        await session.commit()
    games[session_id] = game
    chat_bridge.suspend(session_id)
    logger.info(f"海龟汤：会话 {session_id} 开始新的一局「{puzzle.title}」")
    return game


async def abort_game(game: Game) -> None:
    """开局的开始消息没能发出去时回滚：结束本局、恢复 Chat、删除记录并退回开局费用。"""
    game.finished = True
    games.pop(game.session_id, None)
    chat_bridge.resume(game.session_id)
    try:
        await game.delete_row()
    except Exception:
        logger.opt(exception=True).warning(f"海龟汤：回滚对局记录失败: {game.session_id}")
    # 本局作废就退钱：玩家没有真正玩到这一局
    await wallet.refund(game.owner_id, config.turtle_soup_generate_cost, "开局消息发送失败")


async def record_correct(user_id: str) -> None:
    """正确作答数 +1（排行榜数据），用原子自增避免并发结算丢计数。"""
    now = datetime.now()
    async with get_session() as session:
        result = await session.execute(
            update(TurtleSoupPlayer)
            .where(TurtleSoupPlayer.user_id == user_id)
            .values(correct_count=TurtleSoupPlayer.correct_count + 1, last_correct_time=now),
        )
        if result.rowcount:
            await session.commit()
            return
        session.add(TurtleSoupPlayer(user_id=user_id, correct_count=1, last_correct_time=now))
        try:
            await session.commit()
        except IntegrityError:
            # 同一用户两局同时结算时可能撞上主键：回滚后按已有记录自增
            await session.rollback()
            await session.execute(
                update(TurtleSoupPlayer)
                .where(TurtleSoupPlayer.user_id == user_id)
                .values(correct_count=TurtleSoupPlayer.correct_count + 1, last_correct_time=now),
            )
            await session.commit()


async def _expire_game(game: Game) -> bool:
    """静默结束一局：不发送任何提示。判定进行中时返回 False，留给下一轮清理。"""
    if game.lock.locked():
        return False
    game.finished = True
    games.pop(game.session_id, None)
    chat_bridge.resume(game.session_id)
    try:
        await game.delete_row()
    except Exception:
        logger.opt(exception=True).warning(f"海龟汤：删除过期记录失败: {game.session_id}")
    logger.info(f"海龟汤：会话 {game.session_id} 的本局已过期")
    return True


async def expire_due_games() -> int:
    """清理所有已过期的对局（内存与数据库），返回清理数量。"""
    now = datetime.now()
    expired: list[str] = []
    async with get_session() as session:
        rows = (await session.scalars(select(TurtleSoupGame).where(TurtleSoupGame.expire_time <= now))).all()
        for row in rows:
            game = games.get(row.session_id)
            if game is not None and game.lock.locked():
                # 正在判定：本轮跳过，避免删掉记录后这次提问的结算无处可写
                continue
            expired.append(row.session_id)
            await session.delete(row)
        await session.commit()
    for session_id in expired:
        game = games.pop(session_id, None)
        if game is not None:
            game.finished = True
        chat_bridge.resume(session_id)
    if expired:
        logger.info(f"海龟汤：清理了 {len(expired)} 个过期对局")
    return len(expired)


# ---------- 启动与定时任务 ----------


async def restore_games() -> int:
    """启动时恢复未过期的对局，并重新屏蔽对应会话的 Chat。"""
    now = datetime.now()
    restored = 0
    async with get_session() as session:
        rows = (await session.scalars(select(TurtleSoupGame))).all()
        for row in rows:
            if row.expire_time <= now:
                await session.delete(row)
                continue
            try:
                game = _game_from_row(row)
            except Exception:
                # 出题中途重启留下的占位记录（puzzle_data 为空）也在这里被清掉
                logger.opt(exception=True).warning(f"海龟汤：恢复对局失败，已删除: {row.session_id}")
                await session.delete(row)
                continue
            games[game.session_id] = game
            chat_bridge.suspend(game.session_id)
            restored += 1
        await session.commit()
    if restored:
        logger.info(f"海龟汤：恢复了 {restored} 个进行中的对局")
    return restored


@get_driver().on_startup
async def _restore_on_startup() -> None:
    try:
        await restore_games()
    except Exception:
        logger.opt(exception=True).error("海龟汤：恢复进行中的对局失败")


@scheduler.scheduled_job("interval", minutes=1, id="turtle_soup_expire")
async def _expire_games_job() -> None:
    try:
        await expire_due_games()
    except Exception:
        logger.opt(exception=True).warning("海龟汤：清理过期对局失败")
