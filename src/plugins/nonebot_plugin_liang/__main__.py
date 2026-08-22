from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_larkutils import get_user_id

from .lang import lang

TZ = ZoneInfo("Asia/Shanghai")

alc = Alconna("liang")
liang = on_alconna(alc)

# 梁文峰时段（北京时间）: 9:00-12:00, 14:00-18:00
# 周六周日全天为梁文谷时段，不再区分峰谷
WENFENG_PERIODS = [(9, 12), (14, 18)]

# datetime.weekday(): 周一=0 ... 周六=5, 周日=6
WEEKEND = (5, 6)


def is_weekend(day: datetime) -> bool:
    """判断给定时间是否是周末"""
    return day.weekday() in WEEKEND


def is_wenfeng(now: datetime) -> bool:
    """判断当前时间是否是梁文峰时间"""
    if is_weekend(now):
        return False
    return any(start <= now.hour < end for start, end in WENFENG_PERIODS)


def next_transition(now: datetime) -> tuple[bool, datetime]:
    """计算下一个切换时间点

    周六周日全天为梁文谷时段，不产生切换点。

    Returns:
        (is_next_wenfeng, transition_time)
    """
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 从当天起逐天向后扫描一周，必然覆盖下一个切换点
    for _ in range(8):
        if not is_weekend(day):
            for start, end in WENFENG_PERIODS:
                for hour, next_is_wenfeng in ((start, True), (end, False)):
                    point = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                    if point > now:
                        return next_is_wenfeng, point
        day += timedelta(days=1)
    raise RuntimeError("Unreachable: no transition found within one week")  # pragma: no cover


async def format_countdown(delta: timedelta, user_id: str) -> str:
    """将时间差格式化为 'X 分钟' / 'X 小时 Y 分钟' / 'X 天 Y 小时'"""
    total_minutes = int(delta.total_seconds() // 60)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days:
        return await lang.text("suffix_days_hours", user_id, days, hours)
    if not hours:
        return await lang.text("suffix_minutes", user_id, minutes)
    if not minutes:
        return await lang.text("suffix_hours", user_id, hours)
    return await lang.text("suffix_hours_minutes", user_id, hours, minutes)


@liang.handle()
async def _(user_id: str = get_user_id()) -> None:
    now = datetime.now(TZ)
    current_wenfeng = is_wenfeng(now)
    next_is_wenfeng, transition_time = next_transition(now)
    delta = transition_time - now

    if current_wenfeng:
        current_name = await lang.text(
            "time_wenfeng", user_id, *(hour for period in WENFENG_PERIODS for hour in period)
        )
    elif is_weekend(now):
        current_name = await lang.text("time_wengu_weekend", user_id)
    else:
        current_name = await lang.text("time_wengu", user_id)
    next_name = await lang.text("name_wenfeng" if next_is_wenfeng else "name_wengu", user_id)
    countdown = await format_countdown(delta, user_id)
    emoji = "🔴" if current_wenfeng else "🔵"

    await lang.finish("result", user_id, emoji, current_name, next_name, countdown)
