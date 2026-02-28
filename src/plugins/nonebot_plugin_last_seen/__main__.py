from datetime import datetime
from typing import Optional
from nonebot import on_message, logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Match, At
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkutils import get_user_id, get_group_id, is_private_message
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from .models import LastSeenRecord


# Initialize language helper
lang = LangHelper()

# Constants
GLOBAL_SESSION_ID = "global"


async def update_last_seen(user_id: str, session_id: str) -> None:
    """更新用户的最后上线时间"""
    async with get_session() as session:
        # 查询是否已存在记录
        result = await session.execute(
            select(LastSeenRecord).where(
                LastSeenRecord.user_id == user_id,
                LastSeenRecord.session_id == session_id
            )
        )
        record = result.scalar_one_or_none()
        
        current_time = datetime.now()
        
        if record:
            # 更新现有记录
            record.last_seen = current_time
        else:
            # 创建新记录
            record = LastSeenRecord(
                user_id=user_id,
                session_id=session_id,
                last_seen=current_time
            )
            session.add(record)
        
        await session.commit()


async def get_last_seen(user_id: str, session_id: str) -> Optional[datetime]:
    """获取用户的最后上线时间"""
    async with get_session() as session:
        result = await session.execute(
            select(LastSeenRecord).where(
                LastSeenRecord.user_id == user_id,
                LastSeenRecord.session_id == session_id
            )
        )
        record = result.scalar_one_or_none()
        return record.last_seen if record else None





# Message handler to track last seen time
@on_message(block=False, priority=99).handle()
async def handle_message(
    bot: Bot,
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    is_private: bool = is_private_message()
) -> None:
    """监听所有消息，更新用户的最后上线时间"""
    # 更新全局最后上线时间
    await update_last_seen(user_id, GLOBAL_SESSION_ID)
    
    # 如果不是私聊，更新会话内最后上线时间
    if not is_private:
        await update_last_seen(user_id, group_id)


# Initialize command
lastseen_alc = Alconna("lastseen", Args["user?", At])
lastseen = on_alconna(lastseen_alc)


async def format_time_diff(last_seen: datetime, user_id: str) -> str:
    """格式化时间差"""
    now = datetime.now()
    diff = now - last_seen
    
    total_seconds = int(diff.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    
    if days > 0:
        return await lang.text("time.days", user_id, days, hours, minutes)
    elif hours > 0:
        return await lang.text("time.hours", user_id, hours, minutes)
    else:
        return await lang.text("time.minutes", user_id, minutes)


async def get_last_seen_info(user_id: str, target_user_id: str, session_id: str, label_key: str) -> Optional[dict]:
    """获取最后上线时间信息字典"""
    last_seen = await get_last_seen(target_user_id, session_id)
    if not last_seen:
        return None
    
    time_diff = await format_time_diff(last_seen, user_id)
    formatted_time = last_seen.strftime("%Y-%m-%d %H:%M:%S")
    session_label = await lang.text(f"label.{label_key}", user_id)
    
    return {
        "location": await lang.text("item.location", user_id, session_label),
        "time_diff": await lang.text("item.time_diff", user_id, time_diff),
        "time_point": await lang.text("item.time_point", user_id, formatted_time)
    }

from nonebot_plugin_larkuser.utils.user import get_user

@lastseen.handle()
async def handle_lastseen(
    bot: Bot,
    event: Event,
    user: Match[At],
    sender_id: str = get_user_id(),
    is_private: bool = is_private_message()
) -> None:
    """Handle the /lastseen command"""
    # Determine target user
    target_user_id = sender_id
    if user.available:
        target_user_id = user.result.target
    nickname = get_nickname(target_user_id, bot, event)
    global_info = await get_last_seen_info(sender_id, target_user_id, GLOBAL_SESSION_ID, "global")

    items = []
    
    # Add title if any record found
    if global_info:
        items.append(await lang.text("item.title", sender_id))
        items.append(f"{global_info['location']}")
        items.append(f"{global_info['time_diff']}")
        items.append(f"{global_info['time_point']}")
    
    # Get "here" last seen info (only in group chat)
    if not is_private:
        try:
            group_id = await get_group_id().__call__()
            if group_id:
                here_info = await get_last_seen_info(sender_id, target_user_id, group_id, "here")
                if here_info:
                    # Add empty line separator
                    items.append("")
                    items.append(f"{here_info['location']}")
                    items.append(f"{here_info['time_diff']}")
                    items.append(f"{here_info['time_point']}")
        except Exception:
            pass
    
    # Check if any record found
    if not items:
        await lang.finish("no_record", sender_id)
        return
    
    # Send formatted result
    await lang.finish(
        "result",
        sender_id,
        nickname,
        "\n".join(items)
    )
