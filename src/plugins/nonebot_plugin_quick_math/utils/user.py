import copy
from datetime import datetime
from nonebot_plugin_orm import AsyncSession, get_session

from ..models import QuickMathUser, QuickMathWeek


def get_week_key(now: datetime | None = None) -> str:
    """返回当前时间的 ISO 周标识，如 ``2026-W35``。"""
    now = now or datetime.now()
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


async def update_user_data(user_id: str, point: int) -> tuple[int, int]:
    async with get_session() as session:
        data = await session.get(QuickMathUser, user_id)
        if data is not None:
            record = copy.deepcopy(data.max_point)
            if point > data.max_point:
                data.max_point = point
            data.experience += point * (point / data.max_point)
            data.last_use = datetime.now()
            await session.commit()
            diff = point - record
        else:
            session.add(
                QuickMathUser(
                    user_id=user_id,
                    max_point=point,
                    experience=point,
                    last_use=datetime.now(),
                ),
            )
            await session.commit()
            diff, record = point, 0
        await add_week_points(session, user_id, point)
        return diff, record


async def add_week_points(session: AsyncSession, user_id: str, point: int) -> None:
    """将本次积分累计到当前 ISO 周。"""
    week = get_week_key()
    week_data = await session.get(QuickMathWeek, (user_id, week))
    if week_data is None:
        session.add(QuickMathWeek(user_id=user_id, week=week, points=point))
    else:
        week_data.points += point
    await session.commit()
