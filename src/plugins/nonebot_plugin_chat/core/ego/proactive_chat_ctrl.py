"""主动私聊控制器

在困倦度低于阈值时，每小时检查一次，使用 LLM 寻找发送者和主题。
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_orm import get_session
from pydantic import BaseModel
from sqlalchemy import select

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

from ...models import PrivateChatSession

PROACTIVE_CHECK_INTERVAL = 3600

# 分级冷却时间（小时）：好感度越高，冷却越短
COOLDOWN_TIERS = (0.301, 12.0), (0.151, 24.0), (0.051, 36.0)
# 连续未回复主动私聊达到该次数后不再发起
MAX_UNREPLIED_COUNT = 2


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

    async def check_and_send(self) -> None:
        now = datetime.now()
        if self._last_check_time and (now - self._last_check_time).total_seconds() < PROACTIVE_CHECK_INTERVAL:
            return
        self._last_check_time = now

        if self.moonlark_main.state["sleep_mode"]:
            return
        if self.moonlark_main.sleep_controller.tiredness >= 0.74:
            return

        try:
            candidates = await self._get_candidates()
            if not candidates:
                return

            decision = await self._llm_decide(candidates)
            if decision is None or decision.skip:
                return

            await self._send_proactive(decision)
        except Exception as e:
            logger.exception(f"[ProactiveChat] 检查失败: {e}")

    async def _get_candidates(self) -> dict[str, dict]:
        from nonebot_plugin_larkuser.utils.user import get_user

        candidates = {}
        now = datetime.now().timestamp()
        async with get_session() as db_session:
            all_sessions = (await db_session.execute(select(PrivateChatSession))).scalars().all()

        for session in all_sessions:
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
        return candidates

    async def _llm_decide(self, candidates: dict[str, dict]) -> Optional[ProactiveDecision]:
        from .event_collector import event_collector

        friend_list = "\n".join(f"- {info['nickname']} (好感度: {info['fav']})" for info in candidates.values())
        plan_text = self.moonlark_main.planner.get_plan_text()
        events_text = await event_collector.get_all_events_summary()
        notes_text = await self.moonlark_main.get_relevant_notes()
        messages = await get_messages(
            "proactive_chat",
            friends=friend_list,
            plan=plan_text,
            events=events_text,
            notes=notes_text,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        try:
            return await fetch_json(
                messages,
                ProactiveDecision,
                identify="ProactiveChat - Decide",
                reasoning_effort="low",
            )
        except Exception as e:
            logger.warning(f"[ProactiveChat] LLM 决策失败: {e}")
            return None

    async def _send_proactive(self, decision: ProactiveDecision) -> str:
        from ..proactive_chat import send_proactive_private_message
        from nonebot import get_bot

        async with get_session() as db_session:
            all_sessions = (await db_session.execute(select(PrivateChatSession))).scalars().all()

        for chat_session in all_sessions:
            from nonebot_plugin_larkuser.utils.user import get_user

            user = await get_user(chat_session.user_id)
            if user.get_nickname() == decision.target_nickname:
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
