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
        async with get_session() as db_session:
            all_sessions = (await db_session.execute(select(PrivateChatSession))).scalars().all()

        for session in all_sessions:
            user = await get_user(session.user_id)
            nickname = user.get_nickname()
            fav = user.get_display_fav()
            if fav <= 0:
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
                    return f"已向 {decision.target_nickname} 发送主动私聊"
                except Exception as e:
                    logger.error(f"[ProactiveChat] 发送失败: {e}")
                    return f"发送失败: {e}"

        return f"未找到用户: {decision.target_nickname}"
