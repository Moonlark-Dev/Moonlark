import operator
import random
from datetime import datetime
from typing import Optional

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils.command import get_command_prefix

from ..__main__ import lang
from ..config import config
from ..types import ExtendReplyType, ReplyType
from ..utils.message import wait_answer
from ..utils.session import QuickMathPvpSession
from ..utils.user import update_user_data

# 房间码字符集：去除 0/O/1/I 等易混淆字符
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 5

rooms: dict[str, "QuickMathRoom"] = {}


def generate_room_code() -> str:
    while True:
        code = "".join(random.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
        if code not in rooms:
            return code


def find_room_of_user(user_id: str) -> Optional["QuickMathRoom"]:
    """查找用户当前所在的房间（全局唯一，一个用户同时只能在一个房间中）。"""
    return next((room for room in rooms.values() if room.get_player(user_id) is not None), None)


class QuickMathRoomPlayer:
    def __init__(self, user_id: str, qq_user_id: Optional[str], event: Event) -> None:
        self.user_id = user_id
        self.qq_user_id = qq_user_id
        # 加入房间时的事件，作为该玩家第一题的回复目标，避免所有首题都回复同一条消息
        self.event = event
        self.session: Optional[QuickMathPvpSession] = None
        self.saved = False
        self.final_point = 0


class QuickMathRoom:
    def __init__(self, room_id: str, group_id: str, owner: str, max_players: int, bot: Bot, event: Event) -> None:
        self.room_id = room_id
        self.group_id = group_id
        self.owner = owner
        self.max_players = max_players
        self.bot = bot
        # 房间内最新的事件，用于群内广播（QQ 被动回复需始终针对最新事件）
        self.last_event = event
        self.players: list[QuickMathRoomPlayer] = []
        self.status = "waiting"  # waiting | playing | ended
        self.order: list[QuickMathRoomPlayer] = []
        self.seat = 0

    def get_player(self, user_id: str) -> Optional[QuickMathRoomPlayer]:
        return next((player for player in self.players if player.user_id == user_id), None)

    @property
    def is_full(self) -> bool:
        return len(self.players) >= self.max_players

    async def get_nickname(self, user_id: str) -> str:
        user = await get_user(user_id)
        return user.get_nickname() if user.has_nickname() else await lang.text("rank.default_nickname", user_id)

    async def broadcast_lang(self, key: str, user_id: str, *args: object) -> None:
        """向房间广播本地化文本（QQ 下针对房间的最新事件被动回复）。"""
        await UniMessage(await lang.text(key, user_id, *args)).send(target=self.last_event, bot=self.bot)

    # ---------- 房间消息 ----------

    async def build_create_message(self, user_id: str) -> UniMessage:
        prefix = get_command_prefix()
        join_command = f"{prefix}qm pvp join {self.room_id}"
        if isinstance(self.bot, QQBot):
            return (
                UniMessage()
                .style(await lang.text("pvp.create_md", user_id, self.max_players), "markdown")
                .keyboard(Button("enter", await lang.text("button.pvp-join", user_id), text=join_command))
            )
        return UniMessage(await lang.text("pvp.create", user_id, self.room_id, join_command, self.max_players))

    async def build_player_list_message(self, user_id: str) -> UniMessage:
        lines = [await lang.text("pvp.room_title", user_id, self.room_id, len(self.players), self.max_players)]
        for index, player in enumerate(self.players, start=1):
            nickname = await self.get_nickname(player.user_id)
            if player.user_id == self.owner:
                nickname += await lang.text("pvp.owner_suffix", user_id)
            lines.append(await lang.text("pvp.room_player", user_id, index, nickname))
        if isinstance(self.bot, QQBot):
            prefix = get_command_prefix()
            buttons = [Button("enter", await lang.text("button.pvp-start", user_id), text=f"{prefix}qm pvp start")]
            if not self.is_full:
                buttons.append(
                    Button(
                        "enter",
                        await lang.text("button.pvp-join", user_id),
                        text=f"{prefix}qm pvp join {self.room_id}",
                    ),
                )
            buttons.append(Button("enter", await lang.text("button.pvp-quit", user_id), text=f"{prefix}qm pvp quit"))
            return UniMessage().style("\n".join(lines), "markdown").keyboard(*buttons)
        lines.append(await lang.text("pvp.join_hint", user_id, f"{get_command_prefix()}qm pvp join {self.room_id}"))
        return UniMessage("\n".join(lines))

    # ---------- 对战流程 ----------

    async def start(self) -> None:
        """开始对战：打乱并固定参与顺序，依次轮流向玩家发题。"""
        self.status = "playing"
        random.shuffle(self.players)
        self.order = self.players[:]
        self.seat = 0
        for player in self.players:
            # 升级周期按参与人数计算：人数 × 普通模式升级周期，开局人数固定后不再变化
            player.session = QuickMathPvpSession(
                player.user_id,
                self.bot,
                player.qq_user_id,
                player.event,
                cycle_count=len(self.players) * config.qm_change_max_level_count,
            )
            # 预置玩家加入时的事件，使首题回复针对该玩家的消息而非统一回复同一事件
            player.session.events = [player.event]
        order_text = " → ".join([await self.get_nickname(player.user_id) for player in self.order])
        await self.broadcast_lang("pvp.started", self.owner, order_text, len(self.order))
        while self.status == "playing" and len(self.players) > 1:
            next_player = self.order[self.seat % len(self.order)]
            while self.players and next_player not in self.players:
                self.seat += 1
                next_player = self.order[self.seat % len(self.order)]
            if not self.players:
                break
            self.seat += 1
            if await self.play_turn(next_player) and next_player in self.players:
                self.players.remove(next_player)
        if self.status == "playing":
            await self.finish()

    async def play_turn(self, player: QuickMathRoomPlayer) -> bool:
        """向单个玩家发送题目并处理回答；返回玩家是否被淘汰。"""
        session = player.session
        if session is None:
            return True
        image, question = await session.get_question()
        send_time = datetime.now()
        result = await wait_answer(
            question,
            image,
            player.user_id,
            session.events,
            allow_quit=False,
            # 超时以 PromptTimeout 返回 ReplyType.TIMEOUT，避免 FinishedException 中断整个对战
            ignore_error_details=False,
        )
        if session.events:
            session.event = session.events[-1]
            self.last_event = session.event
        if player.saved:
            # 等待期间玩家已通过 /qm pvp quit 退出或房间已被解散
            return True
        session.total_answered += 1
        if result in (ReplyType.TIMEOUT, ReplyType.WRONG, ExtendReplyType.LEAVE):
            await self.eliminate(player)
            return True
        if result == ReplyType.SKIP and session.available_skip_count > session.skipped_question:
            await session.on_skip(question, send_time)
        elif result == ReplyType.RIGHT:
            await session.on_right_answer(question, send_time)
        await session.on_question_finished()
        return False

    async def eliminate(self, player: QuickMathRoomPlayer, quit_game: bool = False) -> None:
        """保存成绩并广播淘汰/退出消息。"""
        if player.saved:
            return
        player.saved = True
        session = player.session
        player.final_point = session.point if session is not None else 0
        if session is not None and session.passed > 0:
            await update_user_data(player.user_id, session.point)
            await session.update_achievement()
        nickname = await self.get_nickname(player.user_id)
        if quit_game:
            await self.broadcast_lang("pvp.player_quited", self.owner, nickname)
        else:
            await self.broadcast_lang("pvp.eliminated", self.owner, nickname, player.final_point)

    async def finish(self) -> None:
        """仅剩一人时结算：保存成绩并发送得分排行表格（md_to_pic）。"""
        winner = self.players[0] if self.players else None
        if winner is not None and winner.session is not None and winner.session.passed > 0:
            await update_user_data(winner.user_id, winner.session.point)
            await winner.session.update_achievement()
        if winner is not None:
            winner_nickname = await self.get_nickname(winner.user_id)
            await self.broadcast_lang("pvp.winner", self.owner, winner_nickname, winner.session.point)
        image = await md_to_pic(await self.build_result_markdown())
        await UniMessage().image(raw=image).send(target=self.last_event, bot=self.bot)
        self.status = "ended"
        rooms.pop(self.room_id, None)

    async def build_result_markdown(self) -> str:
        """生成结算表格 markdown（按得分降序）。"""
        records: list[dict] = []
        for player in self.order:
            session = player.session
            records.append(
                {
                    "user_id": player.user_id,
                    "point": player.final_point,
                    "passed": session.passed if session is not None else 0,
                    "total_answered": session.total_answered if session is not None else 0,
                    "skipped": session.skipped_question if session is not None else 0,
                },
            )
        records.sort(key=operator.itemgetter("point"), reverse=True)
        lines = [await lang.text("pvp.result_title", self.owner)]
        for index, record in enumerate(records, start=1):
            nickname = await self.get_nickname(record["user_id"])
            rate = record["passed"] / record["total_answered"] * 100 if record["total_answered"] else 0
            lines.append(
                await lang.text(
                    "pvp.result_row",
                    self.owner,
                    index,
                    nickname,
                    record["point"],
                    record["passed"],
                    f"{rate:.0f}%",
                    record["skipped"],
                ),
            )
        return "\n".join(lines)
