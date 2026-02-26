from datetime import datetime, timedelta
from nonebot_plugin_apscheduler import scheduler
from typing import Literal, cast
from nonebot import get_driver, logger
from nonebot.adapters import Bot
from nonebot_plugin_alconna import Target
from nonebot_plugin_larklang.__main__ import get_group_language
from nonebot_plugin_orm import get_session
from ...models import MessageQueueCache
from .base import BaseSession
from .group import GroupSession
from .private import PrivateSession

groups: dict[str, BaseSession] = {}


def get_session_directly(group_id: str) -> BaseSession:
    """
    获取指定群组的 GroupSession 对象

    Args:
        group_id: 群组 ID

    Returns:
        GroupSession 对象

    Raises:
        KeyError: 当群组 Session 不存在时
    """
    return groups[group_id]


async def post_group_event(
    group_id: str, event_prompt: str, trigger_mode: Literal["none", "probability", "all"]
) -> bool:
    """
    向指定群组发送事件

    Args:
        group_id: 群组 ID
        event_prompt: 事件的描述文本
        trigger_mode: 触发模式
            - "none": 不触发回复
            - "probability": 使用概率计算判断是否触发回复
            - "all": 强制触发回复

    Returns:
        bool: 是否成功执行
    """
    try:
        session = get_session_directly(group_id)
        await session.post_event(event_prompt, trigger_mode)
        return True
    except KeyError:
        return False


async def get_private_session(user_id: str, target: Target, bot: Bot) -> PrivateSession:
    if user_id not in groups:
        groups[user_id] = PrivateSession(user_id, bot, target)
        await groups[user_id].setup()
    return cast(PrivateSession, groups[user_id])


async def get_group_session_forced(group_id: str, target: Target, bot: Bot) -> GroupSession:
    """强制获取群会话（如果存在则返回已存在的，否则创建新的）"""
    if group_id not in groups:
        return await create_group_session(group_id, target, bot)
    return cast(GroupSession, groups[group_id])


async def group_disable(group_id: str) -> None:
    if group_id in groups:
        group = groups.pop(group_id)
        group.processor.enabled = False


async def reset_session(session_id: str) -> bool:
    """
    重置指定会话，清除所有历史消息并销毁 Session

    Args:
        session_id: 会话 ID（群组 ID 或用户 ID）

    Returns:
        bool: 是否成功重置
    """
    if session_id not in groups:
        return False
    
    session = groups.pop(session_id)
    session.processor.enabled = False
    
    # 清除消息队列中的所有消息
    session.processor.openai_messages.messages.clear()
    session.processor.openai_messages.inserted_messages.clear()
    
    # 删除数据库中的缓存
    async with get_session() as db_session:
        cache = await db_session.get(MessageQueueCache, {"group_id": session_id})
        if cache:
            await db_session.delete(cache)
            await db_session.commit()
    
    logger.info(f"Session {session_id} has been reset.")
    return True


async def create_group_session(group_id: str, target: Target, bot: Bot) -> GroupSession:
    """创建群会话，并查询群语言设置"""
    if group_id not in groups:
        lang_name = await get_group_language(group_id)
        groups[group_id] = GroupSession(group_id, bot, target, lang_name=lang_name)
        await groups[group_id].setup()
    return cast(GroupSession, groups[group_id])


async def create_private_session(user_id: str, target: Target, bot: Bot) -> PrivateSession:
    if user_id not in groups:
        groups[user_id] = PrivateSession(user_id, bot, target)
        await groups[user_id].setup()
    return cast(PrivateSession, groups[user_id])


@scheduler.scheduled_job("cron", minute="*", id="trigger_group")
async def _() -> None:
    # 清理过期的交互请求
    total_expired_count = 0
    for session in groups.values():
        expired_count = session.cleanup_expired_interactions()
        total_expired_count += expired_count
    logger.debug(f"Will clean up {total_expired_count} expired session.")
    expired_session_id = []
    for session_id, session in groups.items():
        logger.debug(f"Triggering timer from {session_id=}.")
        await session.process_timer()
        if isinstance(session, PrivateSession) and (datetime.now() - session.last_activate) >= timedelta(minutes=15):
            expired_session_id.append(session_id)
    for session_id in expired_session_id:
        session = groups[session_id]
        await session.processor.openai_messages.save_to_db()
        groups.pop(session_id)
        logger.info(f"Session {session_id} expired and removed.")


@get_driver().on_shutdown
async def _() -> None:
    for session in groups.values():
        await session.processor.openai_messages.save_to_db()
