from datetime import datetime, timedelta
from typing import List
from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Match, At
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import get_session
from nonebot_plugin_render import render_template, generate_render_keys
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import select, delete
from .models import OnlineTimeRecord
import asyncio

# Initialize language helper
lang = LangHelper()

# Initialize command
alc = Alconna(
    "online-timer",
    Args["user?", At]
)
online_timer = on_alconna(alc)

# Message handler to track online time
async def is_group_message_and_not_qq(bot: Bot, event: Event) -> bool:
    """Check if message is from group chat and not from QQ adapter"""
    # For now, we'll just check if it's a group message
    # QQ adapter exclusion will be handled by the plugin configuration or adapter-specific logic
    try:
        group_id = event.get_session_id()
        user_id = event.get_user_id()
        # If session_id equals user_id, it's a private message
        return group_id != user_id
    except ValueError:
        return False

# Message handler with priority and blocking
message_handler = on_message(
    rule=is_group_message_and_not_qq,
    priority=10,
    block=False
)

@message_handler.handle()
async def handle_message(
    user_id: str = get_user_id()
):
    """Handle group messages to track user online time"""
    async with get_session() as session:
        # Get the latest record for this user
        stmt = select(OnlineTimeRecord).where(
            OnlineTimeRecord.user_id == user_id
        ).order_by(OnlineTimeRecord.end_time.desc()).limit(1)
        
        result = await session.execute(stmt)
        latest_record = result.scalar_one_or_none()
        
        current_time = datetime.now()
        
        # Check if we should extend the existing session or create a new one
        if latest_record and latest_record.end_time + timedelta(minutes=10) > current_time:
            # Extend the existing session
            latest_record.end_time = current_time + timedelta(minutes=3)
        else:
            # Create a new session
            new_record = OnlineTimeRecord(
                user_id=user_id,
                start_time=current_time,
                end_time=current_time + timedelta(minutes=3)
            )
            session.add(new_record)
        
        await session.commit()

@online_timer.handle()
async def handle_online_timer(
    user: Match[At],
    sender_id: str = get_user_id()
):
    """Handle the /online-timer command"""
    # Determine which user to query
    target_user_id = sender_id
    if user.available:
        target_user_id = user.result.target
    
    # Get online time data for the user
    async with get_session() as session:
        stmt = select(OnlineTimeRecord).where(
            OnlineTimeRecord.user_id == target_user_id
        ).order_by(OnlineTimeRecord.start_time.desc())  # Limit to last 100 records
        
        result = await session.execute(stmt)
        records = result.scalars().all()
    
    # Render timeline
    image_bytes = await render_online_timeline(target_user_id, list(records))
    
    # Send the rendered image
    from nonebot_plugin_alconna.uniseg import UniMessage
    await online_timer.finish(
        UniMessage().image(raw=image_bytes, name="online_timeline.png")
    )

async def render_online_timeline(user_id: str, records: List[OnlineTimeRecord]) -> bytes:
    """Render online timeline as an image"""
    # Prepare data for template
    timeline_data = []
    if records:
        # Get the time range (last 3 days)
        end_time = datetime.now()
        start_time = end_time - timedelta(days=3)
        
        # Filter records within the time range
        filtered_records = [
            record for record in records 
            if record.start_time >= start_time and record.end_time <= end_time
        ]
        
        # Convert to template-friendly format
        for record in filtered_records:
            timeline_data.append({
                "start": record.start_time.isoformat(),
                "end": record.end_time.isoformat()
            })

    # Render template
    return await render_template(
        "online_timer.html.jinja",
        await lang.text("online_timer.title", user_id),
        user_id,
        {
            "records": timeline_data,
            "target_user_id": user_id
        },
        await generate_render_keys(lang, user_id, ["online_timer.title"])
    )

# Scheduled task to clean up old records
@scheduler.scheduled_job("cron", hour=2, minute=0)  # Run daily at 2:00 AM
async def cleanup_old_records():
    """Delete records older than 3 days"""
    async with get_session() as session:
        three_days_ago = datetime.now() - timedelta(days=3)
        stmt = delete(OnlineTimeRecord).where(
            OnlineTimeRecord.end_time < three_days_ago
        )
        await session.execute(stmt)
        await session.commit()

# Import on_shutdown from nonebot
from nonebot import get_driver

@get_driver().on_shutdown
async def cleanup_on_shutdown():
    """Clean up old records when bot shuts down"""
    await cleanup_old_records()
