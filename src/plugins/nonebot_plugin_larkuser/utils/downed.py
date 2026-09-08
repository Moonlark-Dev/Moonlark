from datetime import timedelta

from ..lang import lang


def format_duration(delta: timedelta) -> str:
    """将时长格式化为人类可读文本"""
    total = int(max(0, delta.total_seconds()))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分钟"
    if minutes:
        return f"{minutes}分钟{seconds}秒" if seconds else f"{minutes}分钟"
    return f"{seconds}秒"


async def send_down_prompt(user_id: str, remaining: timedelta) -> None:
    """发送独立的倒地提示"""
    await lang.send("downed.prompt", user_id, format_duration(remaining))
