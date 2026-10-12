#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

"""好感度评价的落库与门控

原先 chat 插件把「上次评价时间 + 当日累计变动」塞在 LarkUser 的 config
（``chat_fav_judge_cache``）里：既看不到评价历史，也没法判断一条消息是不是被
反复拿来刷好感度。现在每次评价都写进 :class:`~nonebot_plugin_chat.models.FavorJudgeRecord`：

- 冷却时间与每日上限直接由这张表推导（不再读写 LarkUser config，也不迁移旧数据）；
- 同一条消息（<=5 字完全匹配，>5 字按 simhash 模糊匹配）出现次数越多，
  Jev 判定「提升好感度」所需的置信度越高，上限 :data:`FAV_JUDGE_CONFIDENCE_MAX`。
  到达上限也只是抬高门槛：只要 Jev 的置信度不低于上限，仍然可以通过，
  不会出现「无论多确信都被拒绝」的硬阻断。

具体数值都在下面的常量里，改动只需要动这一处。
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional

from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

from ..models import FavorJudgeRecord
from .simhash import build_message_fingerprint, count_matching_fingerprints

# 单次评价的好感度步长（score 的每一档）与每日累计变动上限
FAV_JUDGE_STEP = 0.0004
FAV_JUDGE_DAILY_LIMIT = 0.005

# 评价冷却时间（小时）：提升好感度比降低好感度更严格
FAV_JUDGE_COOLDOWN_HOURS_UP = 1.0
FAV_JUDGE_COOLDOWN_HOURS_DOWN = 0.5

# 重复消息的统计窗口与最多回溯的记录数（按时间倒序取，避免大用户量下全表扫描）
FAV_JUDGE_DUPLICATE_WINDOW_DAYS = 30
FAV_JUDGE_DUPLICATE_SCAN_LIMIT = 200

# 置信度抬升：要求 = min(上限, 步长 * 该消息在窗口内出现过的次数)
# 出现 0 次时要求为 0（普通消息完全不受影响）；出现 9 次及以上要求封顶在 0.9
FAV_JUDGE_CONFIDENCE_STEP = 0.1
FAV_JUDGE_CONFIDENCE_MAX = 0.9


@dataclass(frozen=True)
class FavorJudgeState:
    """一次评价前的历史状态，全部由 :class:`FavorJudgeRecord` 推导"""

    last_judge_time: Optional[datetime] = None
    daily_score: float = 0.0
    similar_count: int = 0  # 目标消息在统计窗口内出现过的次数


@dataclass(frozen=True)
class FavorJudgeDecision:
    """门控结论

    ``rejection`` 为 None 表示允许这次变动；否则是拒绝原因的语言键后缀
    （``cooldown`` / ``daily_limit`` / ``low_confidence``）。
    """

    delta: float
    rejection: Optional[str] = None
    required_confidence: float = 0.0
    similar_count: int = 0


def get_cooldown_hours(score: int) -> float:
    """本次评价需要的冷却时间（小时）"""
    return FAV_JUDGE_COOLDOWN_HOURS_UP if score > 0 else FAV_JUDGE_COOLDOWN_HOURS_DOWN


def get_required_confidence(similar_count: int) -> float:
    """重复消息抬高后的置信度要求

    出现 0 次返回 0（普通消息不受影响）；随后每多出现一次抬高
    :data:`FAV_JUDGE_CONFIDENCE_STEP`，封顶在 :data:`FAV_JUDGE_CONFIDENCE_MAX`。
    """
    if similar_count <= 0:
        return 0.0
    return min(FAV_JUDGE_CONFIDENCE_MAX, FAV_JUDGE_CONFIDENCE_STEP * similar_count)


def decide_favor_change(
    score: int,
    confidence: float,
    state: FavorJudgeState,
    now: Optional[datetime] = None,
) -> FavorJudgeDecision:
    """按冷却 / 每日上限 / 重复消息置信度三道门给出结论（纯函数，便于测试）"""
    now = now or datetime.now()
    delta = score * FAV_JUDGE_STEP
    if state.last_judge_time is not None:
        cooldown = timedelta(hours=get_cooldown_hours(score))
        if now - state.last_judge_time < cooldown:
            return FavorJudgeDecision(delta=0.0, rejection="cooldown")
    if abs(state.daily_score + delta) > FAV_JUDGE_DAILY_LIMIT:
        return FavorJudgeDecision(delta=0.0, rejection="daily_limit")
    # 只有「提升好感度」才受重复消息门控影响：降低好感度不需要额外置信度
    if score > 0:
        required = get_required_confidence(state.similar_count)
        if confidence < required:
            return FavorJudgeDecision(
                delta=0.0,
                rejection="low_confidence",
                required_confidence=required,
                similar_count=state.similar_count,
            )
        return FavorJudgeDecision(
            delta=delta,
            required_confidence=required,
            similar_count=state.similar_count,
        )
    return FavorJudgeDecision(delta=delta)


async def get_favor_judge_state(
    user_id: str,
    message_fingerprint: str = "",
    now: Optional[datetime] = None,
) -> FavorJudgeState:
    """读取该用户的历史评价状态

    Args:
        user_id: 用户主账号 ID
        message_fingerprint: 本次目标消息的指纹；为空表示不做重复消息统计
        now: 当前时间（便于测试注入）
    """
    now = now or datetime.now()
    day_start = datetime.combine(now.date(), time.min)
    window_start = now - timedelta(days=FAV_JUDGE_DUPLICATE_WINDOW_DAYS)
    async with get_session() as session:
        last_judge_time = await session.scalar(
            select(func.max(FavorJudgeRecord.created_at)).where(FavorJudgeRecord.user_id == user_id)
        )
        daily_score = await session.scalar(
            select(func.coalesce(func.sum(FavorJudgeRecord.delta), 0.0)).where(
                FavorJudgeRecord.user_id == user_id,
                FavorJudgeRecord.created_at >= day_start,
            )
        )
        similar_count = 0
        if message_fingerprint:
            fingerprints = (
                await session.scalars(
                    select(FavorJudgeRecord.message_key)
                    .where(
                        FavorJudgeRecord.user_id == user_id,
                        FavorJudgeRecord.created_at >= window_start,
                        FavorJudgeRecord.message_key != "",
                    )
                    .order_by(FavorJudgeRecord.created_at.desc())
                    .limit(FAV_JUDGE_DUPLICATE_SCAN_LIMIT)
                )
            ).all()
            similar_count = count_matching_fingerprints(fingerprints, message_fingerprint)
    return FavorJudgeState(
        last_judge_time=last_judge_time,
        daily_score=float(daily_score or 0.0),
        similar_count=similar_count,
    )


async def record_favor_change(
    *,
    user_id: str,
    message: str,
    score: int,
    delta: float,
    session_id: str = "",
    nickname: str = "",
    confidence: float = 0.0,
    reason: str = "",
    now: Optional[datetime] = None,
) -> None:
    """把一次生效的好感度变动写进 :class:`FavorJudgeRecord`"""
    async with get_session() as session:
        session.add(
            FavorJudgeRecord(
                user_id=user_id,
                session_id=session_id[:128],
                nickname=nickname[:128],
                message=message,
                message_key=build_message_fingerprint(message),
                score=score,
                delta=delta,
                confidence=confidence,
                reason=reason,
                created_at=now or datetime.now(),
            )
        )
        await session.commit()
