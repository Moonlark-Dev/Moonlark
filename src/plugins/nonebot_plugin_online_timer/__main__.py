from datetime import datetime, timedelta, date
from typing import List, Optional, NoReturn
from nonebot import on_message, logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Match, At
from nonebot_plugin_larkutils import get_main_account, get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import get_session
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import select, delete, func
from .constants import PROBABILITY_WINDOW_DAYS, RECORD_RETENTION_DAYS
from .heatmap import compute_probability_grid, draw_heatmap
from .models import OnlineTimeRecord
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from nonebot_plugin_ranking import RankingData, generate_image
from nonebot_plugin_alconna.uniseg import UniMessage


async def format_duration(duration: timedelta, user_id: str) -> str:
    total_seconds = int(duration.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return await lang.text("duration.day", user_id, days, hours)
    if hours > 0:
        return await lang.text("duration.hr", user_id, hours, minutes)
    else:
        return await lang.text("duration.minute", user_id, minutes)


# Initialize language helper
lang = LangHelper()

# Initialize command
alc = Alconna("online-timer", Args["subcommand?", str]["user?", At])
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
        result = await session.execute(
            select(OnlineTimeRecord)
            .where(OnlineTimeRecord.user_id == user_id)
            .order_by(OnlineTimeRecord.end_time.desc())
            .limit(1)
        )
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


async def get_sorted_ranking_data() -> list[RankingData]:
    """统计近三天各用户的在线分钟数，按降序返回，供指令与 WebRanking 共用。"""
    # Get the time range (last 3 days)
    start_time = datetime.now() - timedelta(days=3)
    async with get_session() as session:
        stmt = select(OnlineTimeRecord).where(OnlineTimeRecord.start_time >= start_time)
        records = (await session.scalars(stmt)).all()

    # Calculate total online time for each user
    user_online_time: dict[str, timedelta] = {}
    for record in records:
        user_online_time.setdefault(record.user_id, timedelta())
        user_online_time[record.user_id] += record.end_time - record.start_time

    # Convert to minutes, drop empty entries and sort
    user_minutes: list[RankingData] = [
        {"user_id": user_id, "info": None, "data": total_minutes}
        for user_id, total_time in user_online_time.items()
        if (total_minutes := int(total_time.total_seconds() / 60)) > 0
    ]
    user_minutes.sort(key=lambda x: x["data"], reverse=True)
    return user_minutes


async def handle_ranking(sender_id: str) -> NoReturn:
    # Generate ranking image
    return await online_timer.finish(
        UniMessage().image(
            raw=await generate_image(
                await get_sorted_ranking_data(),
                sender_id,
                await lang.text("rank.title", sender_id),
            ),
            name="online_timer_rank.png",
        )
    )


@online_timer.handle()
async def handle_online_timer(subcommand: Match[str], user: Match[At], sender_id: str = get_user_id()):
    """Handle the /online-timer command"""
    # Check if this is a rank command
    if subcommand.available and subcommand.result == "rank":
        await handle_ranking(sender_id)
    # Handle regular online-timer command
    # Determine which user to query
    target_user_id = sender_id
    if user.available:
        # At 拿到的是适配器原生 ID（QQ 官方账号是 openid），而记录按主账号存，先做一次映射
        target_user_id = await get_main_account(user.result.target)

    now = datetime.now()
    window_start = now - timedelta(days=PROBABILITY_WINDOW_DAYS)
    # Get online time data for the user
    # 保留期已扩到一个月，这里按时间窗口取全量记录：近三天的时段图与近一个月的概率图都要用
    async with get_session() as session:
        stmt = (
            select(OnlineTimeRecord)
            .where(OnlineTimeRecord.user_id == target_user_id)
            .where(OnlineTimeRecord.end_time >= window_start)
            .order_by(OnlineTimeRecord.start_time.desc())
        )

        result = await session.scalars(stmt)
        records = result.all()
    logger.debug(records)
    # Render timeline
    image_bytes = await render_online_timeline(target_user_id, list(records), viewer_id=sender_id, now=now)

    # Send the rendered image
    await online_timer.finish(UniMessage().image(raw=image_bytes, name="online_timeline.png"))


CARD_WIDTH = 640
CARD_MARGIN = 24
CONTENT_WIDTH = CARD_WIDTH - CARD_MARGIN * 2
TIME_AXIS_LABELS = ("0:00", "6:00", "12:00", "18:00", "24:00")

# 卡片纵向布局：上半部分是近三天的时段图，下半部分是近一个月的在线概率热力图
TITLE_Y = 18
USER_ID_Y = 50
STATS_Y = 80
TIMELINE_Y = 146
TIMELINE_HEIGHT = 54
HEAT_TITLE_Y = TIMELINE_Y + TIMELINE_HEIGHT + 62
HEAT_LABEL_WIDTH = 40
HEAT_CELL_WIDTH = (CONTENT_WIDTH - HEAT_LABEL_WIDTH) / 24
HEAT_CELL_HEIGHT = 24
HEAT_GRID_Y = HEAT_TITLE_Y + 52
HEAT_LABEL_Y = HEAT_GRID_Y + 7 * HEAT_CELL_HEIGHT + 8
NOW_PROBABILITY_Y = HEAT_LABEL_Y + 24
PROBABILITY_BASIS_Y = NOW_PROBABILITY_Y + 22
LAST_SEEN_Y = PROBABILITY_BASIS_Y + 18


async def render_online_timeline(
    user_id: str,
    records: List[OnlineTimeRecord],
    timeline_date: Optional[date] = None,
    viewer_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bytes:
    """Render online timeline as an image using Pillow

    Args:
        user_id: 被查询的用户
        records: 该用户近一个月的在线记录
        timeline_date: 时段图要画哪一天，默认「今天」
        viewer_id: 触发指令的用户；只有跟被查询的人不同时（也就是 At 别人）才额外显示「现在在线的概率」
        now: 当前时间，默认取 ``datetime.now()``，测试里可以注入
    """
    now = now or datetime.now()
    if timeline_date is None:
        timeline_date = now.date()
    # Get user nickname
    from nonebot_plugin_larkuser.utils.user import get_user

    user = await get_user(user_id)
    nickname = user.get_nickname()
    show_current_probability = viewer_id is not None and viewer_id != user_id

    # Get the time range (last 3 days)
    end_time = (now + timedelta(minutes=3)).replace(hour=23, minute=59, second=59)
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
    # Calculate today and total online time
    today_online_time = daily_online_time.get(timeline_date, timedelta())
    total_online_str = await format_duration(total_online_time, user_id)
    today_online_str = await format_duration(today_online_time, user_id)

    # Create image
    background_color = (255, 255, 255)  # White background
    text_color = (0, 0, 0)  # Black text
    sub_text_color = (120, 120, 120)  # Gray for secondary text
    online_color = (0, 128, 0)  # Green for online time
    offline_color = (128, 128, 128)  # Gray for offline time
    font_path = "./src/static/SarasaGothicSC-Regular.ttf"

    # 只有 At 别人时才会有「现在在线的概率」那几行，图片高度随之变化
    image_height = (LAST_SEEN_Y + 22) if show_current_probability else (HEAT_LABEL_Y + 26)
    image = Image.new("RGB", (CARD_WIDTH, image_height), background_color)
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
    draw.text((CARD_MARGIN, TITLE_Y), title, fill=text_color, font=title_font)

    # Draw user ID
    user_id_text = await lang.text("image.user_id", user_id, user_id)
    draw.text((CARD_MARGIN, USER_ID_Y), user_id_text, fill=text_color, font=small_font)

    # Draw statistics
    draw.text(
        (CARD_MARGIN, STATS_Y),
        await lang.text("image.three_day", user_id, total_online_str),
        fill=text_color,
        font=text_font,
    )
    draw.text(
        (CARD_MARGIN, STATS_Y + 25),
        await lang.text("image.today", user_id, today_online_str),
        fill=text_color,
        font=text_font,
    )

    # Draw timeline
    timeline_start_x = CARD_MARGIN
    timeline_end_x = CARD_MARGIN + CONTENT_WIDTH
    timeline_start_y = TIMELINE_Y
    timeline_end_y = TIMELINE_Y + TIMELINE_HEIGHT

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
        start_x = timeline_start_x + ((record_start_time - day_start_time).total_seconds() / 86400) * CONTENT_WIDTH
        end_x = timeline_start_x + ((record_end_time - day_start_time).total_seconds() / 86400) * CONTENT_WIDTH
        online_width = end_x - start_x
        draw.rectangle([start_x, timeline_start_y, start_x + online_width, timeline_end_y], fill=online_color)

    # Draw time labels below the timeline
    time_labels_y = timeline_end_y + 10  # Position below the timeline
    for i, label in enumerate(TIME_AXIS_LABELS):
        # Calculate position for each label (0, 6, 12, 18, 24 hours)
        label_x = timeline_start_x + (i * CONTENT_WIDTH / (len(TIME_AXIS_LABELS) - 1))
        # Get text width to center the label
        text_width = draw.textbbox((0, 0), label, font=small_font)[2]
        # Draw the label centered at the calculated position
        draw.text((label_x - text_width / 2, time_labels_y), label, fill=text_color, font=small_font)

    # ===== 近一个月的在线概率（热力时间轴）=====
    probability_grid = compute_probability_grid(((record.start_time, record.end_time) for record in records), now)
    weekday_labels = [await lang.text(f"heatmap.weekday{index}", user_id) for index in range(1, 8)]
    draw.text(
        (CARD_MARGIN, HEAT_TITLE_Y),
        await lang.text("heatmap.title", user_id, PROBABILITY_WINDOW_DAYS),
        fill=text_color,
        font=text_font,
    )
    draw_heatmap(
        draw,
        probability_grid,
        now,
        weekday_labels,
        TIME_AXIS_LABELS,
        await lang.text("heatmap.low", user_id),
        await lang.text("heatmap.high", user_id),
        label_font=small_font,
        small_font=small_font,
        left=CARD_MARGIN,
        top=HEAT_GRID_Y,
        label_width=HEAT_LABEL_WIDTH,
        cell_width=HEAT_CELL_WIDTH,
        cell_height=HEAT_CELL_HEIGHT,
    )

    # 「现在在线的概率」只在 At 别人时出现：看自己没必要算，自己在线自己清楚
    if show_current_probability:
        draw.text(
            (CARD_MARGIN, NOW_PROBABILITY_Y),
            await lang.text("heatmap.now_probability", user_id, probability_grid.probability_at(now)),
            fill=text_color,
            font=text_font,
        )
        draw.text(
            (CARD_MARGIN, PROBABILITY_BASIS_Y),
            await lang.text(
                "heatmap.now_probability_basis",
                user_id,
                PROBABILITY_WINDOW_DAYS,
                weekday_labels[now.weekday()],
                f"{now.hour:02d}:00-{now.hour + 1:02d}:00",
            ),
            fill=sub_text_color,
            font=small_font,
        )
        draw.text(
            (CARD_MARGIN, LAST_SEEN_Y),
            await get_last_seen_text(records, now, user_id),
            fill=sub_text_color,
            font=small_font,
        )

    # Save image to bytes
    img_bytes = BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    return img_bytes.getvalue()


async def get_last_seen_text(records: List[OnlineTimeRecord], now: datetime, user_id: str) -> str:
    """「最近在线: X 前」；一条记录都没有时返回「暂无记录」。"""
    last_seen = get_last_seen(records, now)
    if last_seen is None:
        return await lang.text("heatmap.last_seen_none", user_id)
    elapsed = now - last_seen
    if elapsed.total_seconds() < 60:
        return await lang.text("heatmap.last_seen_just_now", user_id)
    return await lang.text("heatmap.last_seen", user_id, await format_duration(elapsed, user_id))


def get_last_seen(records: List[OnlineTimeRecord], now: datetime) -> Optional[datetime]:
    """最近一次在线的时刻。

    记录里的 ``end_time`` 是「最后一次发言 + 3 分钟」，会比当前时间晚一点，这里钳到 ``now``，
    否则刚发过言的人会显示成「3 分钟后在线」。
    """
    end_time = max((record.end_time for record in records), default=None)
    return None if end_time is None else min(end_time, now)


async def is_user_recently_online(user_id: str, minutes: int = 30) -> bool:
    """检查用户是否在指定时间内有过在线记录

    Args:
        user_id: 用户 ID
        minutes: 时间范围（分钟），默认 30 分钟

    Returns:
        如果用户在指定时间内有过在线记录返回 True，否则返回 False
    """
    async with get_session() as session:
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        result = await session.execute(
            select(OnlineTimeRecord)
            .where(OnlineTimeRecord.user_id == user_id)
            .where(OnlineTimeRecord.end_time >= cutoff_time)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


# Scheduled task to clean up old records
@scheduler.scheduled_job("cron", hour=2, minute=0)  # Run daily at 2:00 AM
async def cleanup_old_records():
    """Delete records older than ``RECORD_RETENTION_DAYS``（一个月零一天）"""
    async with get_session() as session:
        expire_before = datetime.now() - timedelta(days=RECORD_RETENTION_DAYS)
        stmt = delete(OnlineTimeRecord).where(OnlineTimeRecord.end_time < expire_before)
        await session.execute(stmt)
        await session.commit()


# Import on_shutdown from nonebot
from nonebot import get_driver


@get_driver().on_shutdown
async def cleanup_on_shutdown():
    """Clean up old records when bot shuts down"""
    await cleanup_old_records()
