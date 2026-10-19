#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################
"""用 Pillow 把回声洞评论渲染成 QQ 聊天截图风格的图片（issue #1033）。

布局紧凑：每条评论只占「昵称行 + 气泡」两行，没有 HTML 模板里的 <hr> 和大段 margin。
"""

import hashlib
import io
from dataclasses import dataclass
from typing import TypedDict

from PIL import Image, ImageDraw, ImageFont
from nonebot.log import logger

FONT_PATH = "./src/static/SarasaGothicSC-Regular.ttf"

CANVAS_WIDTH = 600
PAGE_PAD = 16
AVATAR_SIZE = 40
AVATAR_RADIUS = 12
AVATAR_GAP = 8
NAME_ROW_HEIGHT = 20
NAME_ROW_GAP = 6
COMMENT_GAP = 13
BUBBLE_RADIUS = 9
BUBBLE_PAD_X = 10
BUBBLE_PAD_Y = 7
LINE_HEIGHT = 24
LINE_GAP = 5
NAV_HEIGHT = 48
FOOTER_TOP_GAP = 22

COLOR_BG = (242, 242, 243)  # QQ 聊天浅灰背景
COLOR_NAV = (255, 255, 255)
COLOR_DIVIDER = (226, 226, 228)
COLOR_TITLE = (25, 25, 25)
COLOR_TEXT = (25, 25, 25)
COLOR_NAME = (137, 137, 143)  # QQ 昵称灰
COLOR_META = (153, 153, 158)  # 时间 / 评论号
COLOR_BUBBLE = (255, 255, 255)  # 他人消息气泡

AVATAR_COLORS = (
    (117, 178, 242),
    (242, 148, 125),
    (133, 215, 168),
    (240, 178, 106),
    (177, 161, 247),
    (94, 200, 218),
    (235, 143, 202),
    (167, 172, 240),
)


class CommentView(TypedDict):
    """generate() 在渲染前准备好的单条评论视图数据"""

    nickname: str
    time: str
    id: str
    text: str


@dataclass(frozen=True)
class _Fonts:
    title: ImageFont.FreeTypeFont
    name: ImageFont.FreeTypeFont
    meta: ImageFont.FreeTypeFont
    text: ImageFont.FreeTypeFont
    avatar: ImageFont.FreeTypeFont


def _load_fonts() -> _Fonts:
    try:
        return _Fonts(
            title=ImageFont.truetype(FONT_PATH, 19),
            name=ImageFont.truetype(FONT_PATH, 15),
            meta=ImageFont.truetype(FONT_PATH, 12),
            text=ImageFont.truetype(FONT_PATH, 17),
            avatar=ImageFont.truetype(FONT_PATH, 20),
        )
    except OSError as e:
        logger.warning(f"Failed to load cave comment font, falling back to default: {e}")
        default = ImageFont.load_default()
        return _Fonts(title=default, name=default, meta=default, text=default, avatar=default)


def _avatar_color(nickname: str) -> tuple[int, int, int]:
    digest = hashlib.blake2s(nickname.encode("utf-8"), digest_size=1).digest()
    return AVATAR_COLORS[digest[0] % len(AVATAR_COLORS)]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """CJK 逐字断行（QQ 聊天对中文同样是逐字换行，最紧凑）"""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            if current and draw.textlength(current + char, font=font) > max_width:
                lines.append(current)
                current = char
            else:
                current += char
        lines.append(current)
    return lines


def render_comment_image(title: str, footer: str, comments: list[CommentView]) -> bytes:
    """把评论列表渲染为 QQ 聊天截图风格图片，返回 PNG 字节流"""
    fonts = _load_fonts()
    content_left = PAGE_PAD
    content_right = CANVAS_WIDTH - PAGE_PAD
    indent = content_left + AVATAR_SIZE + AVATAR_GAP
    bubble_max_width = content_right - indent
    title_text_height = 27
    footer_text_height = 17

    textbox = Image.new("RGB", (1, 1))
    probe = ImageDraw.Draw(textbox)

    # 离屏测量：折行、气泡尺寸
    plans: list[dict] = []
    for comment in comments:
        wrapped = _wrap_text(probe, comment["text"], fonts.text, bubble_max_width)
        bubble_width = min(
            max(probe.textlength(line, font=fonts.text) for line in wrapped) + BUBBLE_PAD_X * 2,
            bubble_max_width,
        )
        bubble_height = len(wrapped) * LINE_HEIGHT + (len(wrapped) - 1) * LINE_GAP + BUBBLE_PAD_Y * 2
        plans.append(
            {"comment": comment, "wrapped": wrapped, "bubble_width": bubble_width, "bubble_height": bubble_height},
        )
    textbox.close()

    body_height = COMMENT_GAP + sum(
        NAME_ROW_HEIGHT + NAME_ROW_GAP + plan["bubble_height"] + COMMENT_GAP for plan in plans
    )
    height = NAV_HEIGHT + body_height + FOOTER_TOP_GAP + footer_text_height

    image = Image.new("RGB", (CANVAS_WIDTH, height), COLOR_BG)
    draw = ImageDraw.Draw(image)

    # 顶部导航栏（模拟 QQ 聊天标题栏）
    draw.rectangle([0, 0, CANVAS_WIDTH, NAV_HEIGHT], fill=COLOR_NAV)
    draw.line([0, NAV_HEIGHT - 1, CANVAS_WIDTH, NAV_HEIGHT - 1], fill=COLOR_DIVIDER, width=1)
    title_width = draw.textlength(title, font=fonts.title)
    draw.text(
        ((CANVAS_WIDTH - title_width) / 2, (NAV_HEIGHT - title_text_height) / 2),
        title,
        fill=COLOR_TITLE,
        font=fonts.title,
    )

    y = NAV_HEIGHT + COMMENT_GAP
    for plan in plans:
        comment = plan["comment"]

        # 头像（昵称首字圆角方块，颜色由昵称哈希决定）
        avatar_char = (comment["nickname"] or comment["id"] or "?")[:1]
        avatar_length = draw.textlength(avatar_char, font=fonts.avatar)
        draw.rounded_rectangle(
            [content_left, y, content_left + AVATAR_SIZE, y + AVATAR_SIZE],
            radius=AVATAR_RADIUS,
            fill=_avatar_color(comment["nickname"]),
        )
        draw.text(
            (content_left + (AVATAR_SIZE - avatar_length) / 2, y + (AVATAR_SIZE - 28) / 2),
            avatar_char,
            fill=(255, 255, 255),
            font=fonts.avatar,
        )

        # 昵称行：左侧昵称，右侧时间 + 评论号
        draw.text((indent, y), comment["nickname"], fill=COLOR_NAME, font=fonts.name)
        meta_text = f'{comment["time"]}  {comment["id"]}'
        draw.text(
            (content_right - draw.textlength(meta_text, font=fonts.meta), y + 3),
            meta_text,
            fill=COLOR_META,
            font=fonts.meta,
        )

        # 气泡（白色圆角矩形，QQ 他人消息样式）
        bubble_top = y + NAME_ROW_HEIGHT + NAME_ROW_GAP
        draw.rounded_rectangle(
            [indent, bubble_top, indent + plan["bubble_width"], bubble_top + plan["bubble_height"]],
            radius=BUBBLE_RADIUS,
            fill=COLOR_BUBBLE,
        )
        text_x = indent + BUBBLE_PAD_X
        text_y = bubble_top + BUBBLE_PAD_Y
        for line in plan["wrapped"]:
            draw.text((text_x, text_y), line, fill=COLOR_TEXT, font=fonts.text)
            text_y += LINE_HEIGHT + LINE_GAP

        y = bubble_top + plan["bubble_height"] + COMMENT_GAP

    footer_width = draw.textlength(footer, font=fonts.meta)
    draw.text(
        ((CANVAS_WIDTH - footer_width) / 2, height - footer_text_height),
        footer,
        fill=COLOR_META,
        font=fonts.meta,
    )

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    image.close()
    return buf.getvalue()
