"""ghot 合并版图片卡片渲染。

单张卡片同时包含 `ghot`（当前热度分数与排名）和 `ghot history`（历史热度走势）
的内容：顶部是三个时间窗口的分数与排名指标，底部是逐分钟的热度色带与走势曲线。
"""

import colorsys
from collections.abc import Sequence
from datetime import datetime, timedelta
import io
import itertools

from PIL import Image, ImageDraw, ImageFont
from nonebot.log import logger
from nonebot_plugin_message_summary.models import GroupMessage
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from .score import calculate_heat_score
from ..config import config
from ..lang import lang

FONT_PATH = "./src/static/SarasaGothicSC-Regular.ttf"

CARD_WIDTH = 640
CARD_MARGIN = 24
# 白底深色文字；色带沿用原历史图的黄色系（HSV 44°）
BACKGROUND_COLOR = (252, 253, 255)
TEXT_COLOR_MAIN = (30, 41, 59)
TEXT_COLOR_SUB = (100, 116, 139)
CARD_BORDER_COLOR = (226, 232, 240)
BLOCK_COLOR_HUE = 44 / 360
CURVE_COLOR = (180, 83, 9)
RANK_COLOR = (217, 119, 6)
BOX_COLOR = (241, 245, 249)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception as e:
        logger.warning(f"加载字体 {FONT_PATH} 失败，回退到默认字体: {e}")
        return ImageFont.load_default()


def _heat_color(score: float, max_score: float) -> tuple[int, int, int]:
    """按分数占最大值的比例取黄色系颜色。"""
    ratio = 0 if score <= 0 else min(score / max_score, 1)
    rgb = colorsys.hsv_to_rgb(BLOCK_COLOR_HUE, ratio, 1)
    return tuple(int(x * 255) for x in rgb)  # type: ignore[return-value]


def _next_tens(n: int) -> int:
    if n % 10 == 0:
        return n
    return ((n // 10) + 1) * 10


async def compute_heat_series(
    messages: Sequence[GroupMessage],
) -> tuple[list[datetime], list[int], tuple[datetime, datetime]]:
    """计算逐分钟的热度时间序列，与原 `ghot history` 热力图的算法保持一致。

    Returns:
        (每个整数分钟刻度, 对应热度分数, 消息时间区间首尾)
    """
    timestamps = sorted(message.timestamp for message in messages)
    time_interval = (timestamps[0], timestamps[-1])
    heat_scores: list[int] = []
    time_points: list[datetime] = []
    time_cursor = time_interval[0]
    while time_cursor <= time_interval[1]:
        window_start = max(time_cursor - timedelta(minutes=5), time_interval[0])
        window_end = min(time_cursor + timedelta(minutes=5), time_interval[1])
        window_message_timestamps = [timestamp for timestamp in timestamps if window_start <= timestamp <= window_end]
        heat_scores.append(
            await calculate_heat_score(
                window_message_timestamps,
                time_cursor,
                round((window_end - window_start).total_seconds()),
                config.ghot_max_message_rate,
            ),
        )
        time_points.append(time_cursor)
        time_cursor += timedelta(minutes=1)
    return time_points, heat_scores, time_interval


async def render_ghot_card(
    session: async_scoped_session,
    user_id: str,
    group_ids: Sequence[str],
    scores: Sequence[int],
    rankings: Sequence[int],
) -> bytes:
    """渲染合并版群热度卡片。

    Args:
        session: 数据库会话
        user_id: 触发指令的用户主账号 ID
        group_ids: 同一物理群的全部群键
        scores: 当前热度分数，依次为 1 / 5 / 15 分钟窗口
        rankings: 当前热度排名，依次为 1 / 5 / 15 分钟窗口
    """
    result = await session.scalars(select(GroupMessage).where(GroupMessage.group_id.in_(group_ids)))
    messages = list(result.all())
    if not messages:
        await lang.finish("ghot.no_messages", user_id)

    time_points, heat_scores, time_interval = await compute_heat_series(messages)
    origin_max_score = max(heat_scores)
    # 全窗口热度为 0 时 max_score 会被算成 0，下面按比例取色会除零，这里兜底为 1
    max_score = _next_tens(origin_max_score) or 1

    image = Image.new("RGB", (CARD_WIDTH, 400), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)
    title_font = _load_font(26)
    score_font = _load_font(30)
    text_font = _load_font(16)
    small_font = _load_font(12)
    box_font = _load_font(13)

    # 卡片描边
    draw.rounded_rectangle([4, 4, CARD_WIDTH - 5, 395], radius=18, outline=CARD_BORDER_COLOR, width=2)

    # ===== 顶部：标题与群键 =====
    draw.rectangle([CARD_MARGIN, 30, CARD_MARGIN + 4, 56], fill=RANK_COLOR)
    draw.text((CARD_MARGIN + 16, 28), await lang.text("card.title", user_id), fill=TEXT_COLOR_MAIN, font=title_font)
    draw.text(
        (CARD_MARGIN + 16, 62),
        await lang.text("card.gid", user_id, group_ids[0]),
        fill=TEXT_COLOR_SUB,
        font=small_font,
    )

    # ===== 指标区：三个时间窗口的分数与排名 =====
    boxes_y = 94
    boxes_height = 104
    gap = 16
    box_width = (CARD_WIDTH - CARD_MARGIN * 2 - gap * 2) / 3
    for index, (score, ranking) in enumerate(zip(scores[:3], rankings[:3], strict=True)):
        box_x = CARD_MARGIN + index * (box_width + gap)
        draw.rounded_rectangle(
            [box_x, boxes_y, box_x + box_width, boxes_y + boxes_height],
            radius=12,
            fill=BOX_COLOR,
        )
        box_center_x = box_x + box_width / 2
        label = await lang.text(f"card.win{index + 1}", user_id)
        _draw_centered_text(draw, box_center_x, boxes_y + 12, label, box_font, TEXT_COLOR_SUB)
        _draw_centered_text(draw, box_center_x, boxes_y + 34, str(score), score_font, TEXT_COLOR_MAIN)
        _draw_centered_text(draw, box_center_x, boxes_y + 78, f"#{ranking}", box_font, RANK_COLOR)

    # ===== 历史热度走势 =====
    history_y = boxes_y + boxes_height + 22
    draw.text(
        (CARD_MARGIN, history_y),
        await lang.text(
            "card.history",
            user_id,
            f"{(time_interval[1] - time_interval[0]).total_seconds() / 3600:.1f}",
        ),
        fill=TEXT_COLOR_MAIN,
        font=text_font,
    )

    # 热度色带 + 走势曲线（正文宽度撑满卡片）
    strip_y = history_y + 30
    strip_height = 60
    strip_x = CARD_MARGIN
    strip_width = CARD_WIDTH - CARD_MARGIN * 2
    total_interval_seconds = (time_interval[1] - time_interval[0]).total_seconds()
    # 所有消息时间相同时区间长度为 0，避免除零，整段时间轴按一分钟宽绘制
    width_per_minute = strip_width if total_interval_seconds <= 0 else strip_width / (total_interval_seconds / 60)
    for point, record in zip(time_points, heat_scores, strict=True):
        start_x = (
            strip_x + (point - time_interval[0]).total_seconds() / total_interval_seconds * strip_width
            if total_interval_seconds > 0
            else strip_x
        )
        draw.rectangle(
            [start_x, strip_y, start_x + width_per_minute, strip_y + strip_height],
            fill=_heat_color(record, max_score),
        )

    # 曲线：同一份数据的折线叠加，纵轴按 max_score 归一化
    curve_points: list[tuple[float, float]] = []
    for point, record in zip(time_points, heat_scores, strict=True):
        curve_x = (
            strip_x + (point - time_interval[0]).total_seconds() / total_interval_seconds * strip_width
            if total_interval_seconds > 0
            else strip_x + width_per_minute / 2
        )
        curve_y = strip_y + strip_height - 3 - record / max_score * (strip_height - 6)
        curve_points.append((curve_x, curve_y))
    if len(curve_points) == 1:
        draw.ellipse(
            [curve_points[0][0] - 3, curve_points[0][1] - 3, curve_points[0][0] + 3, curve_points[0][1] + 3],
            fill=CURVE_COLOR,
        )
    for (x1, y1), (x2, y2) in itertools.pairwise(curve_points):
        draw.line([(x1, y1), (x2, y2)], fill=CURVE_COLOR, width=2)

    # 时间轴标签
    labels_y = strip_y + strip_height + 8
    label_count = 6
    delta_t = timedelta(seconds=total_interval_seconds / (label_count - 1))
    for i in range(label_count):
        label_time = time_interval[0] + delta_t * i
        label_x = strip_x + i * strip_width / (label_count - 1)
        _draw_centered_text(draw, label_x, labels_y, label_time.strftime("%H:%M"), small_font, TEXT_COLOR_SUB)

    # 底部信息
    footer_y = labels_y + 22
    draw.text(
        (CARD_MARGIN, footer_y),
        await lang.text("card.max", user_id, origin_max_score, max_score),
        fill=TEXT_COLOR_SUB,
        font=small_font,
    )
    draw.text(
        (CARD_MARGIN, footer_y + 18),
        await lang.text("card.messages", user_id, len(messages)),
        fill=TEXT_COLOR_SUB,
        font=small_font,
    )

    # Save image to bytes
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    return img_bytes.getvalue()


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    y: float,
    text: str,
    font: ImageFont.ImageFont,
    color: tuple[int, int, int],
) -> None:
    """以 (center_x, y) 为顶边中点绘制文本。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    draw.text((center_x - text_width / 2, y), text, fill=color, font=font)
