import colorsys
from collections.abc import Sequence
from datetime import timedelta
import io

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont
from nonebot.log import logger
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_message_summary.models import GroupMessage
from sqlalchemy import select

from .score import calculate_heat_score
from ..lang import lang
from ..config import config


async def render_line_chart(session: async_scoped_session, user_id: str, group_ids: Sequence[str]) -> bytes:
    result = await session.scalars(select(GroupMessage).where(GroupMessage.group_id.in_(group_ids)))
    messages = result.all()

    if not messages:
        await lang.finish("ghot.no_messages", user_id)

    # Get the earliest and latest timestamps
    timestamps = [msg.timestamp for msg in messages]
    earliest_time = min(timestamps)
    latest_time = max(timestamps)

    # Create 10-minute intervals
    interval = timedelta(minutes=10)
    current_time = earliest_time + interval / 2
    time_points = []
    heat_scores = []

    # Calculate heat score for each 10-minute interval
    while current_time <= latest_time:
        # For history, we'll use a 15-minute window (same as the main command)
        window_end = current_time + interval / 2
        window_start = current_time - interval / 2

        # Filter messages within the window
        window_messages = [t for t in timestamps if window_start <= t <= window_end]

        # Calculate heat score using the same algorithm as the main function
        score = await calculate_heat_score(
            window_messages, current_time, round(interval.total_seconds()), config.ghot_max_message_rate
        )
        heat_scores.append(score)
        time_points.append(current_time + interval / 2)

        current_time += interval

    # Create the chart
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(time_points, heat_scores, marker="o", linestyle="-", linewidth=2, markersize=4)
    ax.set_title(await lang.text("history.title", user_id))
    ax.set_xlabel(await lang.text("history.xlabel", user_id))
    ax.set_ylabel(await lang.text("history.ylabel", user_id))
    ax.grid(True, alpha=0.3)

    # Format x-axis as time
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=60))
    ax.tick_params(axis="x", rotation=45)

    # Set y-axis limits
    ax.set_ylim(0, round(max(heat_scores) // 10 * 10 + 10))

    # Adjust layout to prevent label cutoff
    fig.tight_layout()

    # Save to bytes
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def get_next_tens(n: int) -> int:
    if n % 10 == 0:
        return n
    return ((n // 10) + 1) * 10


async def render_heat_chart(session: async_scoped_session, user_id: str, group_ids: Sequence[str]) -> bytes:
    result = await session.scalars(select(GroupMessage).where(GroupMessage.group_id.in_(group_ids)))
    messages = list(result.all())
    heat_scores: list[int] = []
    if not messages:
        await lang.finish("ghot.no_messages", user_id)
    message_sorted_by_time = sorted(messages, key=lambda x: x.timestamp)
    time_interval = message_sorted_by_time[0].timestamp, message_sorted_by_time[-1].timestamp
    time_cursor = time_interval[0]
    while time_cursor <= time_interval[1]:
        start_time = time_cursor - timedelta(minutes=5)
        end_time = time_cursor + timedelta(minutes=5)
        start_time = max(start_time, time_interval[0])
        end_time = min(end_time, time_interval[1])
        window_message_timestamps = [
            message.timestamp for message in messages if start_time <= message.timestamp <= end_time
        ]
        heat_scores.append(
            await calculate_heat_score(
                window_message_timestamps,
                time_cursor,
                round((end_time - start_time).total_seconds()),
                config.ghot_max_message_rate,
            )
        )
        time_cursor += timedelta(minutes=1)
    origin_max_score = max(heat_scores)
    # 全窗口热度为 0 时 max_score 会被算成 0，下面按比例取色会除零，这里兜底为 1
    max_score = get_next_tens(origin_max_score) or 1
    # Create Image
    image_width = 600
    image_height = 270
    background_color = (255, 255, 255)  # White background
    text_color = (0, 0, 0)  # Black text
    font_path = "./src/static/SarasaGothicSC-Regular.ttf"

    # Create image
    image = Image.new("RGB", (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)
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
    title = await lang.text("heat_c.title", user_id)
    draw.text((20, 20), title, fill=text_color, font=title_font)

    # Draw group key
    user_id_text = await lang.text("heat_c.gid", user_id, group_ids[0])
    draw.text((20, 60), user_id_text, fill=text_color, font=small_font)

    # Draw statistics
    stats_y = 90
    draw.text(
        (20, stats_y),
        await lang.text(
            "heat_c.interval", user_id, f"{(time_interval[1] - time_interval[0]).total_seconds() / 3600:.1f}"
        ),
        fill=text_color,
        font=text_font,
    )
    draw.text(
        (20, stats_y + 25),
        await lang.text("heat_c.max", user_id, origin_max_score, max_score),
        fill=text_color,
        font=text_font,
    )

    # Draw timeline
    timeline_y = stats_y + 70
    timeline_height = 50
    timeline_width = image_width - 40
    timeline_start_x = 20
    timeline_start_y = timeline_y

    timeline_end_y = timeline_y + timeline_height
    time_cursor = time_interval[0]
    total_interval_seconds = (time_interval[1] - time_interval[0]).total_seconds()
    # 所有消息时间相同时区间长度为 0，避免除零，整段时间轴按一分钟宽绘制
    width_per_minute = timeline_width if total_interval_seconds <= 0 else timeline_width / (total_interval_seconds / 60)
    for record in heat_scores:
        start_x = (
            timeline_start_x
            + (time_cursor - time_interval[0]).total_seconds() / total_interval_seconds * timeline_width
            if total_interval_seconds > 0
            else timeline_start_x
        )
        block_color_hsv = (44 / 360, record / max_score, 1)
        block_color = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(*block_color_hsv))
        draw.rectangle([start_x, timeline_start_y, start_x + width_per_minute, timeline_end_y], fill=block_color)
        time_cursor += timedelta(minutes=1)

    # Draw time labels below the timeline
    time_labels_y = timeline_end_y + 10  # Position below the timeline

    delta_t = timedelta(seconds=total_interval_seconds / 9)
    time_cursor = time_interval[0]
    time_labels = [(time_cursor + delta_t * i).strftime("%H:%M") for i in range(10)]
    for i, label in enumerate(time_labels):
        label_x = timeline_start_x + (i * timeline_width / 9)
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
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    return img_bytes.getvalue()
