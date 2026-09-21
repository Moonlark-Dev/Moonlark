"""主动私聊控制器

在困倦度低于阈值时，每小时检查一次，使用 LLM 寻找发送者和主题。
"""

from collections import deque
from datetime import datetime, timezone
import time
from typing import TYPE_CHECKING, Any, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_orm import get_session
from pydantic import BaseModel
from sqlalchemy import select

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

from ...models import PrivateChatSession, ProactiveChatRecord

PROACTIVE_CHECK_INTERVAL = 3600

# 分级冷却时间（小时）：好感度越高，冷却越短（已在原有基础上整体延长一倍）
COOLDOWN_TIERS = (0.301, 24.0), (0.151, 48.0), (0.051, 72.0)
# 连续未回复主动私聊达到该次数后不再发起
MAX_UNREPLIED_COUNT = 2
# 决策历史保留条数（供 chat-monitor 展示）
DECISION_HISTORY_LIMIT = 100
# 注入决策提示词的近期主动私聊发送记录条数
RECENT_SEND_HISTORY_LIMIT = 10
# bot 可用性检查结果的缓存时间（秒）：同一次检查流程内多次读取复用，避免反复调用平台接口
BOT_AVAILABILITY_CACHE_TTL = 60


async def get_available_bot_ids() -> Optional[set[str]]:
    """获取当前可用（已连接且状态正常）的 bot ID 集合

    Returns:
        可用 bot ID 集合；返回 None 表示无法判断（nonebot_plugin_bots 不可用），
        调用方应跳过 bot 可用性过滤。
    """
    try:
        from nonebot import get_bots
        from nonebot_plugin_bots import is_bot_online
    except ImportError as e:
        logger.warning(f"[ProactiveChat] 无法加载 bot 状态检查，跳过 bot 在线过滤: {e}")
        return None

    available: set[str] = set()
    for bot_id in get_bots():
        try:
            if await is_bot_online(bot_id):
                available.add(bot_id)
        except Exception as e:
            logger.warning(f"[ProactiveChat] 获取 bot {bot_id} 状态失败: {e}")
    return available


def get_cooldown_hours(favorability: float) -> float:
    """根据好感度获取主动私聊冷却时间（小时）

    好感度 < 0.051 时不允许主动私聊，返回无限大。
    """
    for threshold, hours in COOLDOWN_TIERS:
        if favorability >= threshold:
            return hours
    return float("inf")


class ProactiveDecision(BaseModel):
    skip: bool = True
    target_nickname: str = ""
    topic: str = ""


class ProactiveChatController:
    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self._last_check_time: Optional[datetime] = None
        # 可用 bot 缓存：(bot ID 集合, 获取时间)；集合为 None 表示无法判断
        self._bot_availability: Optional[tuple[Optional[set[str]], float]] = None
        # 每次检查的决策记录（供 chat-monitor 展示与调试）
        self.decision_history: deque[dict[str, Any]] = deque(maxlen=DECISION_HISTORY_LIMIT)

    def _record(self, **info: Any) -> None:
        """记录一次主动私聊检查的决策过程，供 chat-monitor 展示。"""
        self.decision_history.append(
            {"time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), **info},
        )

    async def _get_available_bot_ids(self) -> Optional[set[str]]:
        """获取可用 bot ID 集合（带短缓存，一次检查流程内复用）"""
        now = time.monotonic()
        if self._bot_availability is not None and now - self._bot_availability[1] < BOT_AVAILABILITY_CACHE_TTL:
            return self._bot_availability[0]
        available = await get_available_bot_ids()
        self._bot_availability = (available, now)
        return available

    async def check_and_send(self) -> None:
        now = datetime.now()
        if self._last_check_time and (now - self._last_check_time).total_seconds() < PROACTIVE_CHECK_INTERVAL:
            return
        self._last_check_time = now

        if self.moonlark_main.state["sleep_mode"]:
            self._record(stage="sleep_mode")
            return
        if self.moonlark_main.sleep_controller.tiredness >= 0.74:
            self._record(stage="tiredness", tiredness=round(self.moonlark_main.sleep_controller.tiredness, 3))
            return

        try:
            candidates = await self._get_candidates()
            if not candidates:
                self._record(stage="no_candidates")
                return

            candidate_names = [info["nickname"] for info in candidates.values()]
            decision = await self._llm_decide(candidates)
            if decision is None:
                self._record(
                    stage="decision",
                    error="LLM 决策失败",
                    candidates_count=len(candidates),
                    candidates=candidate_names,
                )
                return
            if decision.skip:
                self._record(
                    stage="decision",
                    skip=True,
                    candidates_count=len(candidates),
                    candidates=candidate_names,
                )
                return

            result = await self._send_proactive(decision)
            self._record(
                stage="send",
                skip=False,
                target_nickname=decision.target_nickname,
                topic=decision.topic,
                candidates_count=len(candidates),
                result=result,
            )
        except Exception as e:
            logger.exception(f"[ProactiveChat] 检查失败: {e}")
            self._record(stage="error", error=str(e))

    async def _get_candidates(self) -> dict[str, dict]:
        from nonebot_plugin_larkuser.utils.user import get_user

        candidates = {}
        now = datetime.now().timestamp()
        available_bots = await self._get_available_bot_ids()
        unavailable_users: list[str] = []
        async with get_session() as db_session:
            all_sessions = (await db_session.execute(select(PrivateChatSession))).scalars().all()

        for session in all_sessions:
            # 记录对应的 bot 当前不可用（未连接或状态异常）时无法发送主动私聊，不作为候选
            if available_bots is not None and session.bot_id not in available_bots:
                unavailable_users.append(session.user_id)
                continue
            user = await get_user(session.user_id)
            nickname = user.get_nickname()
            fav = user.get_display_fav()
            if fav <= 0:
                continue
            # 好感度过低，不允许主动私聊
            cooldown_hours = get_cooldown_hours(fav)
            if cooldown_hours == float("inf"):
                continue
            # 处于分级冷却期内，不参与候选
            if session.last_proactive_message_time is not None:
                elapsed = now - session.last_proactive_message_time
                if elapsed < cooldown_hours * 3600:
                    continue
            # 连续多次未回复主动私聊，不再发起
            if session.unreplied_count >= MAX_UNREPLIED_COUNT:
                continue
            candidates[session.user_id] = {
                "nickname": nickname,
                "fav": fav,
                "last_message_time": session.last_message_time,
            }
        if unavailable_users:
            # 记录因 bot 不可用而跳过的用户，供 chat-monitor 排查
            self._record(stage="bot_unavailable", users=unavailable_users)
        return candidates

    async def _get_recent_sends(self) -> str:
        """获取最近若干次主动私聊的发送记录（时间 + 对象 + 内容）"""
        stmt = (
            select(ProactiveChatRecord)
            .order_by(ProactiveChatRecord.sent_at.desc(), ProactiveChatRecord.id.desc())
            .limit(RECENT_SEND_HISTORY_LIMIT)
        )
        async with get_session() as db_session:
            records = (await db_session.scalars(stmt)).all()

        if not records:
            return "暂无主动私聊发送记录。"

        lines = []
        # 查询时按时间倒序取最近 N 条，展示时恢复为时间正序
        for record in reversed(records):
            target = record.nickname or record.user_id
            lines.append(f"- [{record.sent_at.strftime('%m-%d %H:%M')}] 给 {target}: {record.content}")
        return "\n".join(lines)

    async def _llm_decide(self, candidates: dict[str, dict]) -> Optional[ProactiveDecision]:
        from .event_collector import event_collector

        friend_list = "\n".join(f"- {info['nickname']} (好感度: {info['fav']})" for info in candidates.values())
        plan_text = self.moonlark_main.planner.get_plan_text()
        # 只取上次决策之后新产生的事件，避免重复喂入已经决策过的旧事件
        cursor = event_collector.get_decision_cursor()
        events_text = await event_collector.get_events_summary_since(cursor)
        notes_text = await self.moonlark_main.get_relevant_notes()
        recent_sends_text = await self._get_recent_sends()
        messages = await get_messages(
            "proactive_chat",
            friends=friend_list,
            plan=plan_text,
            events=events_text,
            notes=notes_text,
            recent_sends=recent_sends_text,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        try:
            decision = await fetch_json(
                messages,
                ProactiveDecision,
                identify="ProactiveChat - Decide",
                reasoning_effort="low",
            )
        except Exception as e:
            logger.warning(f"[ProactiveChat] LLM 决策失败: {e}")
            return None
        # 仅在真正完成一次决策后推进游标，事件不会因为决策失败而丢失
        event_collector.advance_decision_cursor()
        return decision

    async def _send_proactive(self, decision: ProactiveDecision) -> str:
        from ..proactive_chat import send_proactive_private_message
        from nonebot import get_bot

        available_bots = await self._get_available_bot_ids()
        async with get_session() as db_session:
            all_sessions = (await db_session.execute(select(PrivateChatSession))).scalars().all()

        bot_unavailable = False
        for chat_session in all_sessions:
            from nonebot_plugin_larkuser.utils.user import get_user

            user = await get_user(chat_session.user_id)
            if user.get_nickname() == decision.target_nickname:
                # 该记录对应的 bot 当前不可用，尝试下一个同名记录
                if available_bots is not None and chat_session.bot_id not in available_bots:
                    logger.warning(
                        f"[ProactiveChat] bot {chat_session.bot_id} 当前不可用，"
                        f"跳过用户 {chat_session.user_id} 的主动私聊",
                    )
                    bot_unavailable = True
                    continue
                try:
                    bot = get_bot(chat_session.bot_id)
                    await send_proactive_private_message(bot, chat_session.user_id, decision.topic)
                    logger.info(f"[ProactiveChat] 已向 {decision.target_nickname} 发送主动私聊: {decision.topic}")
                except Exception as e:
                    logger.error(f"[ProactiveChat] 发送失败: {e}")
                    return f"发送失败: {e}"
                # 连续未回复计数 +1（用户任意回复私聊消息时由 update_reply_status 重置）
                try:
                    chat_session.unreplied_count += 1
                    async with get_session() as db_session:
                        await db_session.merge(chat_session)
                        await db_session.commit()
                except Exception as e:
                    logger.warning(f"[ProactiveChat] 更新未回复计数失败: {e}")
                return f"已向 {decision.target_nickname} 发送主动私聊"

        if bot_unavailable:
            return f"{decision.target_nickname} 没有可用的 bot 在线"
        return f"未找到用户: {decision.target_nickname}"

    async def update_reply_status(self, user_id: str) -> None:
        """用户向 bot 发送任意私聊消息时调用，重置连续未回复计数"""
        try:
            async with get_session() as db_session:
                chat_session = (
                    await db_session.execute(select(PrivateChatSession).where(PrivateChatSession.user_id == user_id))
                ).scalar_one_or_none()
                if chat_session is not None and chat_session.unreplied_count > 0:
                    chat_session.unreplied_count = 0
                    await db_session.commit()
        except Exception as e:
            logger.exception(f"[ProactiveChat] update_reply_status 失败: {e}")
