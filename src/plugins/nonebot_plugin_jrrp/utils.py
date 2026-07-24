from datetime import date, datetime, timedelta, timezone

from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .lang import lang
from .models import LuckTrend
from .types import LuckType


def _today() -> date:
    """返回当前 UTC+8 日期。"""
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date()


def get_luck_type(luck_value: int) -> LuckType:
    if luck_value > 100:
        return LuckType.BEYOND_PERFECT
    if luck_value == 100:
        return LuckType.PERFECT_LUCK
    if luck_value == 99:
        return LuckType.ALMOST_PERFECT
    if luck_value >= 85:
        return LuckType.GREAT_DAY
    if luck_value >= 71:
        return LuckType.GOOD_DAY
    if luck_value >= 57:
        return LuckType.FAIR_DAY
    if luck_value >= 43:
        return LuckType.AVERAGE_DAY
    if luck_value >= 29:
        return LuckType.BELOW_AVERAGE
    if luck_value >= 15:
        return LuckType.POOR_DAY
    if luck_value >= 1:
        return LuckType.BAD_DAY
    return LuckType.TERRIBLE_LUCK


async def get_luck_message(user_id: str) -> str:
    luck_value = await get_luck_value(user_id)
    return await lang.text(f"message.{get_luck_type(luck_value).name.lower()}", user_id, luck_value)


async def save_luck_trend(user_id: str, luck_value: int, reroll_count: int = 0) -> None:
    """记录今日人品值到走势表"""
    async with get_session() as session:
        record = LuckTrend(
            user_id=user_id,
            record_date=_today(),
            luck_value=luck_value,
            reroll_count=reroll_count,
        )
        await session.merge(record)
        await session.commit()


async def get_luck_trend(
    user_id: str,
    days: int = 7,
) -> list[LuckTrend]:
    """获取用户最近 N 天的人品走势数据"""
    since = _today() - timedelta(days=days - 1)
    async with get_session() as session:
        result = await session.scalars(
            select(LuckTrend)
            .where(LuckTrend.user_id == user_id, LuckTrend.record_date >= since)
            .order_by(LuckTrend.record_date.asc()),
        )
        return list(result.all())
