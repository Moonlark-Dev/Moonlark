"""烫手山芋的房间与游戏流程。"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Literal, Optional

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import At, Button, UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import escape_cmd_input, escape_markdown
from nonebot_plugin_larkutils.command import get_command_prefix
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import RankingData
from sqlalchemy import select

from .lang import lang
from .logic import (
    Action,
    draw_initial_probability,
    draw_probability,
    get_reward,
    get_risk_level,
    roll_explosion,
)
from .models import SweetPotatoStat
from .potatoes import PotatoType

MIN_PLAYERS = 2
MAX_PLAYERS = 8
# 持有者连续 60s 没有任何操作会爆炸
TURN_TIMEOUT_SECONDS = 60
# 游戏结束后，房间在 5 分钟无操作后自动解散
ENDED_ROOM_TIMEOUT_SECONDS = 300
# 被爆的玩家扣除的血量
BURN_HP_PENALTY = 10

RoomStatus = Literal["waiting", "playing", "ended"]
BurnReason = Literal["pass", "hold", "timeout"]

rooms: dict[str, "HotPotatoRoom"] = {}


@dataclass
class PotatoPlayer:
    user_id: str
    # 适配器原生 ID（QQ 官方为群成员 openid，OneBot 为 QQ 号），用于 @ 玩家
    native_id: Optional[str]
    nickname: str


@dataclass
class PotatoAction:
    turn: int
    kind: Action
    target: Optional[PotatoPlayer] = None


class HotPotatoRoom:
    def __init__(self, group_id: str, owner: str, bot: Bot, event: Event, potato_type: PotatoType) -> None:
        self.group_id = group_id
        self.owner = owner
        self.bot = bot
        # 房间内最新的事件：QQ 官方被动回复需要针对最新事件
        self.last_event = event
        self.potato_type = potato_type
        self.players: list[PotatoPlayer] = []
        self.status: RoomStatus = "waiting"
        self.holder: Optional[PotatoPlayer] = None
        self.probability = 0
        self.min_probability = 0
        self.turn = 0
        self.total_holds = 0
        self.total_passes = 0
        self.holds: dict[str, int] = {}
        self.passes: dict[str, int] = {}
        self.successful_holds: dict[str, int] = {}
        self.pending_holds: dict[str, int] = {}
        self.rewards: dict[str, int] = {}
        self.burned: Optional[PotatoPlayer] = None
        self.burn_reason: Optional[BurnReason] = None
        self.action_queue: asyncio.Queue[PotatoAction] = asyncio.Queue()
        self.game_task: Optional[asyncio.Task[None]] = None
        self.dissolve_task: Optional[asyncio.Task[None]] = None
        self.finishing = False

    # ---------- 玩家 ----------

    def add_player(self, user_id: str, native_id: Optional[str], nickname: str) -> PotatoPlayer:
        player = PotatoPlayer(user_id=user_id, native_id=native_id, nickname=nickname)
        self.players.append(player)
        return player

    def get_player(self, user_id: str) -> Optional[PotatoPlayer]:
        return next((player for player in self.players if player.user_id == user_id), None)

    def remove_player(self, player: PotatoPlayer) -> None:
        if player in self.players:
            self.players.remove(player)

    @property
    def is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS

    def update_event(self, event: Event) -> None:
        self.last_event = event

    def get_pass_targets(self) -> list[tuple[int, PotatoPlayer]]:
        """返回可传递对象及其房间序号（1 起）。"""
        if self.holder is None:
            return []
        return [(index, player) for index, player in enumerate(self.players, start=1) if player is not self.holder]

    def resolve_target(self, value: object) -> Optional[PotatoPlayer]:
        """把 @ 或序号解析为房间内的可传递对象，无效时返回 None。"""
        if self.holder is None or value is None:
            return None
        targets = [player for _, player in self.get_pass_targets()]
        if isinstance(value, At):
            for player in targets:
                if (player.native_id and player.native_id == value.target) or player.user_id == value.target:
                    return player
            return None
        text = str(value).strip()
        if text.lower() in {"random", "r", "随机"}:
            return random.choice(targets) if targets else None
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(self.players):
                player = self.players[index - 1]
                return player if player is not self.holder else None
        return None

    # ---------- 发送 ----------

    async def send(self, message: UniMessage, event: Optional[Event] = None) -> None:
        try:
            await message.send(target=event or self.last_event, bot=self.bot)
        except Exception:
            logger.opt(exception=True).warning(f"烫手山芋：向会话 {self.group_id} 发送消息失败")

    async def send_lang(self, key: str, *args: object, event: Optional[Event] = None) -> None:
        await self.send(UniMessage(await lang.text(key, self.owner, *args)), event)

    # ---------- 房间卡片 ----------

    async def build_room_markdown(self, user_id: str, header: Optional[str] = None, markdown: bool = True) -> str:
        sections: list[str] = []
        if header:
            sections.append(header)
        sections.append(await lang.text("room.title" if markdown else "room.title_plain", user_id))
        sections.append(await lang.text("room.count", user_id, len(self.players), MAX_PLAYERS))
        player_lines: list[str] = []
        for index, player in enumerate(self.players, start=1):
            marks = ""
            if player.user_id == self.owner:
                marks += await lang.text("room.owner_mark", user_id)
            if player.user_id == user_id:
                marks += await lang.text("room.self_mark", user_id)
            nickname = escape_markdown(player.nickname) if markdown else player.nickname
            player_lines.append(await lang.text("room.player", user_id, index, nickname, marks))
        sections.append("\n".join(player_lines))
        sections.append(await lang.text("room.ended_hint" if self.status == "ended" else "room.waiting_hint", user_id))
        return "\n\n".join(section for section in sections if section)

    async def build_room_message(self, user_id: str, header: Optional[str] = None) -> UniMessage:
        if isinstance(self.bot, QQBot):
            markdown = await self.build_room_markdown(user_id, header, markdown=True)
            prefix = get_command_prefix()
            if self.status == "ended":
                buttons = [
                    Button("enter", await lang.text("button.restart", user_id), text=f"{prefix}sweet-potato restart"),
                    Button("enter", await lang.text("button.quit", user_id), text=f"{prefix}sweet-potato quit"),
                ]
            else:
                buttons = [
                    Button("enter", await lang.text("button.join", user_id), text=f"{prefix}sweet-potato join"),
                    Button("enter", await lang.text("button.start", user_id), text=f"{prefix}sweet-potato start"),
                    Button("enter", await lang.text("button.quit", user_id), text=f"{prefix}sweet-potato quit"),
                ]
                if self.is_full:
                    buttons.pop(0)
            return UniMessage().style(markdown, "markdown").keyboard(*buttons, row=2)
        text = await self.build_room_markdown(user_id, header, markdown=False)
        return UniMessage(text)

    async def send_room_card(self, event: Event, user_id: str, header: Optional[str] = None) -> None:
        self.update_event(event)
        await self.send(await self.build_room_message(user_id, header), event)

    # ---------- 游戏面板 ----------

    def get_risk_name(self) -> str:
        return f"risk.{get_risk_level(self.probability)}"

    async def build_panel_markdown(self, summary: str) -> str:
        holder = self.holder
        if holder is None:
            return ""
        risk = await lang.text(self.get_risk_name(), holder.user_id)
        at = f'<qqbot-at-user id="{holder.native_id}" />\n\n' if holder.native_id else ""
        target_lines: list[str] = []
        for index, player in self.get_pass_targets():
            command = f"{get_command_prefix()}sweet-potato pass {index}"
            target_lines.append(
                await lang.text(
                    "game.panel_target_line",
                    holder.user_id,
                    index,
                    escape_cmd_input(command),
                    escape_cmd_input(player.nickname),
                ),
            )
        if not target_lines:
            target_lines.append(await lang.text("game.no_targets", holder.user_id))
        return await lang.text(
            "game.panel_markdown",
            holder.user_id,
            at=at,
            summary=summary,
            risk=risk,
            targets="\n".join(target_lines),
        )

    async def build_panel_text(self, summary: str) -> str:
        holder = self.holder
        if holder is None:
            return ""
        risk = await lang.text(self.get_risk_name(), holder.user_id)
        target_lines = [f"{index}. {player.nickname}" for index, player in self.get_pass_targets()]
        if not target_lines:
            target_lines.append(await lang.text("game.no_targets", holder.user_id))
        return await lang.text(
            "game.panel_text",
            holder.user_id,
            summary=summary,
            risk=risk,
            targets="\n".join(target_lines),
        )

    async def build_panel_message(self, summary: str) -> UniMessage:
        holder = self.holder
        if holder is None:
            return UniMessage()
        if isinstance(self.bot, QQBot):
            markdown = await self.build_panel_markdown(summary)
            prefix = get_command_prefix()
            return (
                UniMessage()
                .style(markdown, "markdown")
                .keyboard(
                    Button(
                        "enter",
                        await lang.text("button.random_pass", holder.user_id),
                        text=f"{prefix}sweet-potato pass random",
                    ),
                    Button("enter", await lang.text("button.hold", holder.user_id), text=f"{prefix}sweet-potato hold"),
                    # 一行仅有一个按钮
                    row=1,
                )
            )
        message = UniMessage()
        if holder.native_id:
            message = message.at(holder.native_id)
        return message.text(await self.build_panel_text(summary))

    # ---------- 游戏流程 ----------

    def reset_game(self) -> None:
        self.status = "playing"
        self.burned = None
        self.burn_reason = None
        self.turn = 0
        self.total_holds = 0
        self.total_passes = 0
        self.holds = {}
        self.passes = {}
        self.successful_holds = {}
        self.pending_holds = {}
        self.rewards = {}
        self.action_queue = asyncio.Queue()
        self.holder = random.choice(self.players)
        initial = draw_initial_probability(self.potato_type.initial_probability_range)
        self.probability = initial
        self.min_probability = initial

    def begin(self) -> None:
        self.reset_game()
        self.cancel_dissolve()
        self.game_task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await self.run_game()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.opt(exception=True).error(f"烫手山芋：会话 {self.group_id} 的游戏循环异常")
            await self.abort()

    async def run_game(self) -> None:
        summary_key = "game.summary_start"
        summary_args: tuple[object, ...] = ()
        while self.status == "playing" and self.holder is not None:
            self.turn += 1
            summary = await lang.text(summary_key, self.holder.user_id, *summary_args)
            await self.send(await self.build_panel_message(summary))
            action = await self.wait_action()
            if action is None:
                await self.finish(self.holder, "timeout")
                return
            if action.kind == "pass":
                if action.target is None:
                    # 理论上不会发生（处理器会先校验目标），忽略空目标避免误执行「捂热」
                    continue
                passer = self.holder
                if not self.pass_potato(action.target):
                    await self.finish(passer, "pass")
                    return
                summary_key = "game.summary_passed"
                summary_args = (passer.nickname,)
            else:
                holder = self.holder
                if not self.hold_potato():
                    await self.finish(holder, "hold")
                    return
                summary_key = "game.summary_hold"
                summary_args = ()

    async def wait_action(self) -> Optional[PotatoAction]:
        """等待当前持有者的操作，超过 60s 返回 None（爆炸）。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + TURN_TIMEOUT_SECONDS
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                action = await asyncio.wait_for(self.action_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            # 丢弃上一回合残留的操作
            if action.turn == self.turn:
                return action

    def submit_action(self, kind: Action, target: Optional[PotatoPlayer] = None) -> bool:
        if self.status != "playing" or self.holder is None:
            return False
        if kind == "pass" and target is None:
            return False
        self.action_queue.put_nowait(PotatoAction(turn=self.turn, kind=kind, target=target))
        return True

    def add_reward(self, player: PotatoPlayer, amount: int) -> None:
        if amount > 0:
            self.rewards[player.user_id] = self.rewards.get(player.user_id, 0) + amount

    def pass_potato(self, target: PotatoPlayer) -> bool:
        """按当前概率判定传递；返回是否成功（False 表示持有者被烫到）。"""
        holder = self.holder
        if holder is None:
            return False
        reward = get_reward(self.probability, "pass")
        if roll_explosion(self.probability):
            return False
        self.total_passes += 1
        self.passes[holder.user_id] = self.passes.get(holder.user_id, 0) + 1
        # 成功把山芋传出去，此前累计的「捂热」才算成功捂热
        pending = self.pending_holds.pop(holder.user_id, 0)
        self.successful_holds[holder.user_id] = self.successful_holds.get(holder.user_id, 0) + pending
        self.holder = target
        self.probability, self.min_probability = draw_probability(self.min_probability, after_pass=True)
        self.add_reward(holder, reward)
        return True

    def hold_potato(self) -> bool:
        """重新抽取爆炸概率；返回是否成功（False 表示抽到 100% 立即爆炸）。"""
        holder = self.holder
        if holder is None:
            return False
        reward = get_reward(self.probability, "hold")
        probability, new_min = draw_probability(self.min_probability)
        if probability >= 100:
            return False
        self.probability = probability
        self.min_probability = new_min
        self.total_holds += 1
        self.holds[holder.user_id] = self.holds.get(holder.user_id, 0) + 1
        self.pending_holds[holder.user_id] = self.pending_holds.get(holder.user_id, 0) + 1
        self.add_reward(holder, reward)
        return True

    # ---------- 结算 ----------

    async def finish(self, burned: Optional[PotatoPlayer], reason: Optional[BurnReason]) -> None:
        if self.finishing or self.status == "ended":
            return
        self.finishing = True
        self.burned = burned
        self.burn_reason = reason
        try:
            await self.apply_settlement()
            await self.send(await self.build_result_message())
        finally:
            self.status = "ended"
            self.finishing = False
            self.game_task = None
            self.schedule_dissolve()

    async def apply_settlement(self) -> None:
        """结算：被爆者 -10 HP，所有玩家统一发放本局累计的 vi。"""
        for player in self.players:
            user = await get_user(player.user_id)
            if player is self.burned:
                await user.damage(BURN_HP_PENALTY)
            reward = self.rewards.get(player.user_id, 0)
            if reward > 0:
                await user.add_vimcoin(reward)
        await self.save_stats()

    async def save_stats(self) -> None:
        async with get_session() as session:
            for player in self.players:
                row = await session.get(SweetPotatoStat, player.user_id)
                if row is None:
                    row = SweetPotatoStat(
                        user_id=player.user_id,
                        successful_holds=0,
                        total_holds=0,
                        total_passes=0,
                        burn_count=0,
                        game_count=0,
                    )
                    session.add(row)
                row.successful_holds += self.successful_holds.get(player.user_id, 0)
                row.total_holds += self.holds.get(player.user_id, 0)
                row.total_passes += self.passes.get(player.user_id, 0)
                row.burn_count += 1 if player is self.burned else 0
                row.game_count += 1
            await session.commit()

    async def build_result_markdown(self) -> str:
        sections = [await lang.text("result.title", self.owner)]
        if self.burned is not None:
            reason_keys = {
                "pass": "result.reason_pass",
                "hold": "result.reason_hold",
                "timeout": "result.reason_timeout",
            }
            sections.append(
                "\n".join(
                    [
                        await lang.text("result.burned", self.owner, self.burned.nickname),
                        await lang.text(reason_keys.get(self.burn_reason, "result.reason_unknown"), self.owner),
                        await lang.text("result.penalty", self.owner, BURN_HP_PENALTY),
                    ],
                ),
            )
        sections.append(await lang.text("result.counts", self.owner, self.total_holds, self.total_passes))
        reward_lines = [await lang.text("result.reward_title", self.owner)]
        for player in self.players:
            mark = await lang.text("result.burned_mark", self.owner) if player is self.burned else ""
            reward_lines.append(
                await lang.text(
                    "result.reward_row",
                    self.owner,
                    player.nickname,
                    self.holds.get(player.user_id, 0),
                    self.passes.get(player.user_id, 0),
                    self.rewards.get(player.user_id, 0),
                    mark,
                ),
            )
        sections.append("\n".join(reward_lines))
        return "\n\n".join(sections)

    async def build_result_message(self) -> UniMessage:
        markdown = await self.build_result_markdown()
        if isinstance(self.bot, QQBot):
            prefix = get_command_prefix()
            return (
                UniMessage()
                .style(markdown, "markdown")
                .keyboard(
                    Button("enter", await lang.text("button.quit", self.owner), text=f"{prefix}sweet-potato quit"),
                    Button(
                        "enter",
                        await lang.text("button.restart", self.owner),
                        text=f"{prefix}sweet-potato restart",
                    ),
                    # 一行仅有一个按钮
                    row=1,
                )
            )
        hint = await lang.text("result.hint_plain", self.owner)
        return UniMessage().text(hint).image(raw=await md_to_pic(markdown))

    # ---------- 房间生命周期 ----------

    async def abort(self) -> None:
        await self.send_lang("room.aborted")
        self.dissolve()

    def cancel_dissolve(self) -> None:
        task = self.dissolve_task
        self.dissolve_task = None
        if task is not None and not task.done():
            task.cancel()

    def schedule_dissolve(self) -> None:
        self.cancel_dissolve()
        self.dissolve_task = asyncio.create_task(self._auto_dissolve())

    async def _auto_dissolve(self) -> None:
        try:
            await asyncio.sleep(ENDED_ROOM_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return
        if rooms.get(self.group_id) is not self or self.status != "ended":
            return
        # 清掉自身引用，避免 dissolve 取消当前任务
        self.dissolve_task = None
        self.dissolve()
        await self.send_lang("room.auto_disbanded")

    def dissolve(self) -> None:
        self.cancel_dissolve()
        game_task = self.game_task
        self.game_task = None
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if game_task is not None and not game_task.done() and game_task is not current:
            game_task.cancel()
        rooms.pop(self.group_id, None)

    def touch_ended(self) -> None:
        """游戏结束后房间内仍有操作时，重置自动解散计时。"""
        if self.status == "ended":
            self.schedule_dissolve()


def get_room(group_id: str) -> Optional[HotPotatoRoom]:
    return rooms.get(group_id)


async def get_rank_data(user_id: str) -> list[RankingData]:
    """成功捂热次数排行数据。"""
    async with get_session() as session:
        rows = list(
            await session.scalars(
                select(SweetPotatoStat)
                .where(SweetPotatoStat.successful_holds > 0)
                .order_by(SweetPotatoStat.successful_holds.desc()),
            ),
        )
    return [
        {
            "user_id": row.user_id,
            "data": row.successful_holds,
            "info": await lang.text(
                "rank.info",
                user_id,
                row.total_holds,
                row.total_passes,
                row.burn_count,
                row.game_count,
            ),
        }
        for row in rows
    ]
