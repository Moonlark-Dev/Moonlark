"""主动私聊控制器

在困倦度低于阈值时，每小时检查一次，使用 LLM 寻找发送者和主题。
"""

from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_orm import get_session
from pydantic import BaseModel
from sqlalchemy import select

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

from ...config import config
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


def get_cooldown_hours(favorability: float) -> float:
    """根据好感度获取主动私聊冷却时间（小时）

    好感度 < 0.051 时不允许主动私聊，返回无限大。
    """
    for threshold, hours in COOLDOWN_TIERS:
        if favorability >= threshold:
            return hours
    return float("inf")


def get_user_active_cooldown_hours() -> float:
    """用户主动私聊后的静默时长（小时）

    返回 0 或负数表示不启用该限制。
    """
    return float(config.proactive_chat_user_active_cooldown_hours)


def is_user_recently_active(chat_session: PrivateChatSession, now: Optional[float] = None) -> bool:
    """判断用户是否在「私聊静默期」内

    用户在静默期内主动私聊过 Moonlark，此时不应再向其发起主动私聊，
    以免在用户刚刚主动找过 Moonlark 后立刻反向打扰。
    """
    cooldown_hours = get_user_active_cooldown_hours()
    if cooldown_hours <= 0:
        return False
    last_message_time = chat_session.last_message_time
    if not last_message_time:
        return False
    if now is None:
        now = datetime.now().timestamp()
    return now - last_message_time < cooldown_hours * 3600


class ProactiveDecision(BaseModel):
    skip: bool = True
    target_nickname: str = ""
    topic: str = ""


class ProactiveChatController:
    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self._last_check_time: Optional[datetime] = None
        # 每次检查的决策记录（供 chat-monitor 展示与调试）
        self.decision_history: deque[dict[str, Any]] = deque(maxlen=DECISION_HISTORY_LIMIT)

    def _record(self, **info: Any) -> None:
        """记录一次主动私聊检查的决策过程，供 chat-monitor 展示。"""
        self.decision_history.append(
            {"time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), **info},
        )

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
            candidates, skipped = await self._get_candidates()
            if not candidates:
                self._record(stage="no_candidates", skipped=skipped)
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

            result = await self._send_proactive(decision, candidates)
            self._record(
                stage="send",
                skip=False,
                target_nickname=decision.target_nickname,
                topic=decision.topic,
                candidates_count=len(candidates),
                skipped=skipped,
                result=result,
            )
        except Exception as e:
            logger.exception(f"[ProactiveChat] 检查失败: {e}")
            self._record(stage="error", error=str(e))

    async def _get_candidates(self) -> tuple[dict[str, dict], dict[str, int]]:
        """筛选本次可以发起主动私聊的候选人

        Returns:
            (候选人字典, 各筛除原因对应的人数统计)
        """
        from nonebot_plugin_larkuser.utils.user import get_user

        candidates: dict[str, dict] = {}
        skipped = {"favorability": 0, "cooldown": 0, "user_active": 0, "unreplied": 0}
        now = datetime.now().timestamp()
        async with get_session() as db_session:
            all_sessions = (await db_session.execute(select(PrivateChatSession))).scalars().all()

        for session in all_sessions:
            user = await get_user(session.user_id)
            nickname = user.get_nickname()
            fav = user.get_display_fav()
            cooldown_hours = get_cooldown_hours(fav)
            # 好感度过低或未建立好感度，不允许主动私聊
            if fav <= 0 or cooldown_hours == float("inf"):
                skipped["favorability"] += 1
                continue
            # 处于分级冷却期内，不参与候选
            if session.last_proactive_message_time is not None:
                elapsed = now - session.last_proactive_message_time
                if elapsed < cooldown_hours * 3600:
                    skipped["cooldown"] += 1
                    continue
            # 用户刚刚主动私聊过：静默期内不主动打扰
            if is_user_recently_active(session, now):
                skipped["user_active"] += 1
                continue
            # 连续多次未回复主动私聊，不再发起
            if session.unreplied_count >= MAX_UNREPLIED_COUNT:
                skipped["unreplied"] += 1
                continue
            candidates[session.user_id] = {
                "nickname": nickname,
                "fav": fav,
                "last_message_time": session.last_message_time,
            }
        if candidates or any(skipped.values()):
            logger.debug(f"[ProactiveChat] 候选筛选结果: candidates={len(candidates)} skipped={skipped}")
        return candidates, skipped

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

    async def _send_proactive(self, decision: ProactiveDecision, candidates: dict[str, dict]) -> str:
        """向决策选中的用户发送主动私聊

        只允许向本次筛选出的候选人发送，并在真正发送前重新确认用户是否刚私聊过，
        避免 LLM 编造昵称或决策期间用户刚发过消息时仍然打扰对方。
        """
        from nonebot import get_bot

        from ..proactive_chat import send_proactive_private_message

        target_user_id = next(
            (user_id for user_id, info in candidates.items() if info["nickname"] == decision.target_nickname),
            None,
        )
        if target_user_id is None:
            logger.warning(f"[ProactiveChat] 决策目标 {decision.target_nickname!r} 不在候选人列表中，已忽略")
            return f"未找到用户: {decision.target_nickname}"

        async with get_session() as db_session:
            chat_session = (
                await db_session.execute(select(PrivateChatSession).where(PrivateChatSession.user_id == target_user_id))
            ).scalar_one_or_none()

        if chat_session is None:
            return f"未找到用户: {decision.target_nickname}"

        # 发送前再次校验：LLM 决策期间用户可能刚私聊过
        if is_user_recently_active(chat_session):
            logger.info(f"[ProactiveChat] 用户 {decision.target_nickname} 刚刚私聊过，跳过本次主动私聊")
            return f"用户 {decision.target_nickname} 刚刚私聊过，已跳过"

        try:
            bot = get_bot(chat_session.bot_id)
            await send_proactive_private_message(bot, chat_session.user_id, decision.topic)
            logger.info(f"[ProactiveChat] 已向 {decision.target_nickname} 发送主动私聊: {decision.topic}")
        except Exception as e:
            logger.error(f"[ProactiveChat] 发送失败: {e}")
            return f"发送失败: {e}"
        # 连续未回复计数 +1（用户任意回复私聊消息时由 update_reply_status 重置）
        try:
            async with get_session() as db_session:
                db_chat_session = (
                    await db_session.execute(
                        select(PrivateChatSession).where(PrivateChatSession.user_id == target_user_id),
                    )
                ).scalar_one_or_none()
                if db_chat_session is not None:
                    db_chat_session.unreplied_count += 1
                    await db_session.commit()
        except Exception as e:
            logger.warning(f"[ProactiveChat] 更新未回复计数失败: {e}")
        return f"已向 {decision.target_nickname} 发送主动私聊"

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
