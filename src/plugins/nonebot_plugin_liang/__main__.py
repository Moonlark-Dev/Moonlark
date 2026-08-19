from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_larkutils import get_user_id

from .lang import lang

TZ = ZoneInfo("Asia/Shanghai")

alc = Alconna("liang")
liang = on_alconna(alc)

# 梁文峰时段（北京时间）: 9:00-12:00, 14:00-18:00
WENFENG_PERIODS = [(9, 12), (14, 18)]


def is_wenfeng(hour: int, minute: int) -> bool:
    """判断当前时间是否是梁文峰时间"""
    for start, end in WENFENG_PERIODS:
        if start <= hour < end:
            return True
    return False


def next_transition(now: datetime) -> tuple[bool, datetime]:
    """计算下一个切换时间点

    Returns:
        (is_next_wenfeng, transition_time)
    """
    h, m = now.hour, now.minute

    if is_wenfeng(h, m):
        # 当前是梁文峰时间，下一个切换是梁文谷
        for start, end in WENFENG_PERIODS:
            if start <= h < end:
                return False, now.replace(hour=end, minute=0, second=0, microsecond=0)
        # fallback
        return False, now.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        # 当前是梁文谷时间，下一个切换是梁文峰
        for start, _ in WENFENG_PERIODS:
            if h < start:
                return True, now.replace(hour=start, minute=0, second=0, microsecond=0)
        # 18:00 之后，下一个是明天 9:00
        tomorrow = now + timedelta(days=1)
        return True, tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)


def format_countdown(delta: timedelta) -> str:
    """将时间差格式化为 'X 分钟' 或 'X 小时 Y 分钟'"""
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes < 60:
        return f"{total_minutes} 分钟"
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if minutes == 0:
        return f"{hours} 小时"
    return f"{hours} 小时 {minutes} 分钟"


@liang.handle()
async def _(user_id: str = get_user_id()) -> None:
    now = datetime.now(TZ)
    current_wenfeng = is_wenfeng(now.hour, now.minute)
    next_is_wenfeng, transition_time = next_transition(now)
    delta = transition_time - now

    current_name = "梁文峰" if current_wenfeng else "梁文谷"
    next_name = "梁文峰" if next_is_wenfeng else "梁文谷"
    countdown = format_countdown(delta)

    await lang.finish("result", user_id, current_name, next_name, countdown)
