from typing import Any

from nonebot.adapters import Event
from nonebot.log import logger
from nonebot.params import Depends
from .subaccount import get_main_account


async def _get_user_id(event: Event) -> str:
    try:
        user_id = event.get_user_id()
    except (ValueError, NotImplementedError):
        # 心跳、生命周期等元事件以及部分通知事件不携带用户上下文，
        # 适配器会在这里抛出 ValueError / NotImplementedError。
        # Alconna 事件响应器的 type 为空，其规则会对所有事件求值，
        # 因此这类事件属于正常情况而不是错误：不记录 ERROR（否则每次心跳
        # 都会输出一条带堆栈的错误），只留一条 trace 供排查。
        logger.trace(f"事件 {event.get_type()} 不包含用户 ID，使用 -1 作为占位")
        return "-1"
    return await get_main_account(user_id)


async def private_message(event: Event) -> bool:
    """判断当前消息是否为私聊

    通用的判断方式是比较 event.get_session_id() 和 event.get_user_id()，
    但某些适配器（如 QQ Bot 的 C2C）的 session ID 包含前缀，无法直接比较。
    这里针对已知的适配器做额外判断。
    """
    try:
        if event.get_session_id() == event.get_user_id():
            return True
    except (ValueError, NotImplementedError):
        pass
    # QQ Bot C2C（私聊）消息：session_id 带有 "c2c_" 前缀，不能直接比较
    if event.__class__.__module__.startswith("nonebot.adapters.qq"):
        from nonebot.adapters.qq.event import C2CMessageCreateEvent

        if isinstance(event, C2CMessageCreateEvent):
            return True
    return False


def get_user_id() -> Any:
    return Depends(_get_user_id)


def is_private_message() -> bool:
    return Depends(private_message)
