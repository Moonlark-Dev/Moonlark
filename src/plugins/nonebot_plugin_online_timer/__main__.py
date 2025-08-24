from datetime import datetime, timedelta, date
from typing import List, Optional
from nonebot import on_message, logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Match, At
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import get_session
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import select, delete
from .models import OnlineTimeRecord
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


async def format_duration(duration: timedelta, user_id: str) -> str:
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return await lang.text("duration.hr", user_id, hours, minutes)
    else:
        return await lang.text("duration.minute", user_id, hours, minutes)


# Initialize language helper
lang = LangHelper()

# Initialize command
alc = Alconna("online-timer", Args["user?", At])
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
message_handler = on_message(rule=is_group_message_and_not_qq, priority=10, block=False)


@message_handler.handle()
async def handle_message(user_id: str = get_user_id()):
    """Handle group messages to track user online time"""
    async with get_session() as session:
        # Get the latest record for this user
        stmt = (
            select(OnlineTimeRecord)
            .where(OnlineTimeRecord.user_id == user_id)
            .order_by(OnlineTimeRecord.end_time.desc())
            .limit(1)
        )

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
                user_id=user_id, start_time=current_time, end_time=current_time + timedelta(minutes=3)
            )
            session.add(new_record)

        await session.commit()


@online_timer.handle()
async def handle_online_timer(user: Match[At], sender_id: str = get_user_id()):
    """Handle the /online-timer command"""
    # Determine which user to query
    target_user_id = sender_id
    if user.available:
        target_user_id = user.result.target

    # Get online time data for the user
    async with get_session() as session:
        stmt = (
            select(OnlineTimeRecord)
            .where(OnlineTimeRecord.user_id == target_user_id)
            .order_by(OnlineTimeRecord.start_time.desc())
            .limit(200)
        )

        result = await session.scalars(stmt)
        records = result.all()
    logger.debug(records)
    # Render timeline
    image_bytes = await render_online_timeline(target_user_id, list(records))

    # Send the rendered image
    from nonebot_plugin_alconna.uniseg import UniMessage

    await online_timer.finish(UniMessage().image(raw=image_bytes, name="online_timeline.png"))


async def render_online_timeline(
    user_id: str, records: List[OnlineTimeRecord], timeline_date: Optional[date] = None
) -> bytes:
    """Render online timeline as an image using Pillow"""
    if timeline_date is None:
        timeline_date = date.today()
    # Get user nickname
    from nonebot_plugin_larkuser.utils.user import get_user

    user = await get_user(user_id)
    nickname = user.get_nickname()

    # Get the time range (last 3 days)
    end_time = (datetime.now() + timedelta(minutes=3)).replace(hour=23, minute=59, second=59)
    start_time = (end_time - timedelta(days=3, minutes=3)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Filter records within the time range
    filtered_records = [
        record
        for record in records
        if start_time <= record.start_time <= end_time or start_time <= record.end_time <= end_time
    ]

    # Calculate statistics
    total_online_time = timedelta()
    daily_online_time = {}  # day -> total time for that day

    for record in filtered_records:
        # Calculate the time this record contributes to online time
        record_duration = record.end_time - record.start_time
        total_online_time += record_duration

        # Group by day for daily statistics
        day = record.start_time.date()
        if day not in daily_online_time:
            daily_online_time[day] = timedelta()
        daily_online_time[day] += record_duration
    logger.debug(f"{filtered_records=} {start_time=} {end_time=}")
    # Calculate average and total online time
    average_daily_online = total_online_time / 3 if daily_online_time else timedelta()
    total_online_str = await format_duration(total_online_time, user_id)
    average_daily_str = await format_duration(average_daily_online, user_id)

    # Create image
    image_width = 600
    image_height = 270
    background_color = (255, 255, 255)  # White background
    text_color = (0, 0, 0)  # Black text
    online_color = (0, 128, 0)  # Green for online time
    offline_color = (128, 128, 128)  # Gray for offline time
    font_path = "./src/static/SarasaGothicSC-Regular.ttf"

    # Create image
    image = Image.new("RGB", (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)

    # Load fonts
    try:
        # Try to load the custom font
        title_font = ImageFont.truetype(font_path, 24)
        text_font = ImageFont.truetype(font_path, 16)
        small_font = ImageFont.truetype(font_path, 12)
    except Exception as e:
        logger.exception(e)
        # Fallback to default font if custom font fails
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Draw title
    title = await lang.text("image.title", user_id, nickname)
    draw.text((20, 20), title, fill=text_color, font=title_font)

    # Draw user ID
    user_id_text = await lang.text("image.user_id", user_id, user_id)
    draw.text((20, 60), user_id_text, fill=text_color, font=small_font)

    # Draw statistics
    stats_y = 90
    draw.text(
        (20, stats_y), await lang.text("image.three_day", user_id, total_online_str), fill=text_color, font=text_font
    )
    draw.text(
        (20, stats_y + 25), await lang.text("image.avg", user_id, average_daily_str), fill=text_color, font=text_font
    )

    # Draw timeline
    timeline_y = stats_y + 70
    timeline_height = 50
    timeline_width = image_width - 40
    timeline_start_x = 20
    timeline_end_x = timeline_start_x + timeline_width
    timeline_start_y = timeline_y
    timeline_end_y = timeline_y + timeline_height

    # Draw timeline background (gray for offline)
    draw.rectangle([timeline_start_x, timeline_start_y, timeline_end_x, timeline_end_y], fill=offline_color)

    for record in [
        item for item in filtered_records if timeline_date in [item.start_time.date(), item.end_time.date()]
    ]:
        day_start_time = datetime(
            year=timeline_date.year,
            month=timeline_date.month,
            day=timeline_date.day,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        day_end_time = datetime(
            year=timeline_date.year,
            month=timeline_date.month,
            day=timeline_date.day,
            hour=23,
            minute=59,
            second=59,
            microsecond=999,
        )
        record_start_time = record.start_time if record.start_time.date() == timeline_date else day_start_time
        record_end_time = record.end_time if record.end_time.date() == timeline_date else day_end_time
        start_x = timeline_start_x + ((record_start_time - day_start_time).total_seconds() / 86400) * timeline_width
        end_x = timeline_start_x + ((record_end_time - day_start_time).total_seconds() / 86400) * timeline_width
        online_width = end_x - start_x
        draw.rectangle([start_x, timeline_start_y, start_x + online_width, timeline_end_y], fill=online_color)

    # Draw time labels below the timeline
    time_labels_y = timeline_end_y + 10  # Position below the timeline
    time_labels = ["0:00", "6:00", "12:00", "18:00", "24:00"]
    for i, label in enumerate(time_labels):
        # Calculate position for each label (0, 6, 12, 18, 24 hours)
        label_x = timeline_start_x + (i * timeline_width / 4)
        # Get text width to center the label
        try:
            text_bbox = draw.textbbox((0, 0), label, font=small_font)
            text_width = text_bbox[2] - text_bbox[0]
        except Exception as e:
            logger.exception(e)
            # Fallback if textbbox is not available
            text_width = len(label) * 6  # Approximate width
        # Draw the label centered at the calculated position
        draw.text((label_x - text_width / 2, time_labels_y), label, fill=text_color, font=small_font)

    # Save image to bytes
    img_bytes = BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    return img_bytes.getvalue()


# Scheduled task to clean up old records
@scheduler.scheduled_job("cron", hour=2, minute=0)  # Run daily at 2:00 AM
async def cleanup_old_records():
    """Delete records older than 3 days"""
    async with get_session() as session:
        three_days_ago = datetime.now() - timedelta(days=3)
        stmt = delete(OnlineTimeRecord).where(OnlineTimeRecord.end_time < three_days_ago)
        await session.execute(stmt)
        await session.commit()


# Import on_shutdown from nonebot
from nonebot import get_driver


@get_driver().on_shutdown
async def cleanup_on_shutdown():
    """Clean up old records when bot shuts down"""
    await cleanup_old_records()
