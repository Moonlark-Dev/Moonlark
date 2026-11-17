"""今日人品卡（Pillow 绘制）。

浅色二次元风格：左侧大字号展示人品值，下方是这一档运势的一句话；右侧是对应的
Moonlark 插画。六档运势与 ``nonebot_plugin_sign`` 的 ``_get_luck`` 完全一致
（>80 / 61-80 / 41-60 / 21-40 / 1-20 / 0 以下）；人品值 >= 100 时保持「大吉」
分档，同时插画与卡片配色切到专属的橙色背景满值版本。
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from .lang import lang
from .utils import get_luck_type

# ---------------------------------------------------------------------------
# 画布与素材
# ---------------------------------------------------------------------------
CARD_WIDTH = 920
CARD_HEIGHT = 580
CARD_BOX = (24, 20, 896, 560)
CARD_RADIUS = 34

_FONT_NAME = "SarasaGothicSC-Regular.ttf"
_ILLUSTRATION_DIR = ("jrrp", "moonlark")
_STATIC_ROOTS = (
    Path(__file__).resolve().parents[2] / "static",  # src/static
    Path("src/static"),
)

Color = tuple[int, int, int]
_WHITE: Color = (255, 255, 255)


@dataclass(frozen=True)
class _Palette:
    """一档运势的配色：深色用于文字，accent 用于渐变与星点，tint 用于胶囊底。"""

    deep: Color
    accent: Color
    tint: Color
    soft: Color


# 配色尽量贴近每张插画自己的背景：橙（>=100）/ 黄 / 蓝 / 绿 / 紫 / 灰蓝 / 深紫
_PALETTES: dict[str, _Palette] = {
    "perfect": _Palette((0xB8, 0x4E, 0x08), (0xFA, 0x94, 0x3A), (0xFF, 0xEE, 0xDE), (0xFF, 0xDC, 0xBD)),
    "a": _Palette((0xA2, 0x66, 0x0A), (0xF0, 0xB8, 0x38), (0xFF, 0xF3, 0xD6), (0xFF, 0xE7, 0xA8)),
    "b": _Palette((0x2A, 0x67, 0xA2), (0x7C, 0xC4, 0xFF), (0xE7, 0xF3, 0xFF), (0xD7, 0xEC, 0xFF)),
    "c": _Palette((0x2D, 0x78, 0x4B), (0x8C, 0xD9, 0x8F), (0xE9, 0xF8, 0xE4), (0xDC, 0xF3, 0xD5)),
    "d": _Palette((0x66, 0x46, 0xA2), (0xB4, 0x97, 0xEE), (0xF0, 0xE9, 0xFC), (0xE7, 0xDB, 0xF8)),
    "e": _Palette((0x43, 0x57, 0x80), (0x97, 0xAC, 0xD5), (0xEC, 0xF0, 0xF9), (0xE1, 0xE7, 0xF4)),
    "f": _Palette((0x56, 0x33, 0x88), (0xA4, 0x82, 0xD8), (0xEF, 0xE7, 0xFA), (0xE4, 0xD8, 0xF5)),
}

_BODY = (0x54, 0x50, 0x68)
_MUTED = (0xA0, 0x99, 0xB2)

# 一句话折行时不允许落在行首的标点（避头点）
_NO_LINE_START = set("，。！？、；：）」』”’…～")
# 允许在其后断行的标点
_BREAK_AFTER = set("，。！？；：、")
# 超过 100 时不再展示 / 100，避免「150 / 100」看起来像出错
_MAX_LUCK = 100


def _static_file(*parts: str) -> Path:
    for root in _STATIC_ROOTS:
        path = root.joinpath(*parts)
        if path.is_file():
            return path
    raise FileNotFoundError(f"缺少 jrrp 卡片素材: {'/'.join(parts)}")


@lru_cache
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_static_file(_FONT_NAME)), size)


# ---------------------------------------------------------------------------
# 运势分级（与 nonebot_plugin_sign 的 _get_luck 保持一致）
# ---------------------------------------------------------------------------
def get_fortune_key(luck_value: int) -> str:
    """人品值 → a~f 六档运势，边界与签到插件相同。"""
    if luck_value > 80:
        return "a"
    if luck_value > 60:
        return "b"
    if luck_value > 40:
        return "c"
    if luck_value > 20:
        return "d"
    if luck_value > 0:
        return "e"
    return "f"


def get_illustration_key(luck_value: int) -> str:
    """人品值 → 插画文件名（不含扩展名）；>= 100 用橙底满值插画，其余按 a~f 六档。"""
    if luck_value >= _MAX_LUCK:
        return "perfect"
    return get_fortune_key(luck_value)


@dataclass(frozen=True)
class CardTexts:
    """卡片上所有需要本地化的文字。"""

    title: str
    unit: str
    unit_max: str
    fortune: str
    phrase: str


def _today() -> date:
    """与 jrrp 的其他入口一致，按 UTC+8 取日期。"""
    return datetime.now(UTC).astimezone(timezone(timedelta(hours=8))).date()


async def render_luck_card(user_id: str, luck_value: int) -> bytes:
    """渲染今日人品卡，返回 PNG 字节。"""
    key = get_fortune_key(luck_value)
    # 卡面上的句子按 jrrp 的 11 档文案取，完整句子（含分值占位）都写在
    # card.phrase.<tier> 里，这里只负责把分值 format 进去，不在代码里改标点。
    tier = get_luck_type(luck_value).name.lower()
    texts = CardTexts(
        title=await lang.text("card.title", user_id),
        unit=await lang.text("card.unit", user_id),
        unit_max=await lang.text("card.unit_max", user_id),
        fortune=await lang.text(f"card.fortune.{key}", user_id),
        phrase=await lang.text(f"card.phrase.{tier}", user_id, luck_value),
    )
    # Pillow 是同步阻塞的，放到线程里跑，避免卡住事件循环
    return await asyncio.to_thread(render_card_image, luck_value, key, texts, _today().strftime("%Y.%m.%d"))


# ---------------------------------------------------------------------------
# 绘图工具
# ---------------------------------------------------------------------------
def _mix(color: Color, other: Color, ratio: float) -> Color:
    """把 color 向 other 混合 ratio（0 = 原色，1 = 全 other）。"""
    return tuple(round(c + (o - c) * ratio) for c, o in zip(color, other))


def _linear_gradient(size: tuple[int, int], top: Color, bottom: Color) -> Image.Image:
    mask = Image.linear_gradient("L").resize(size, Image.Resampling.BICUBIC)
    return ImageOps.colorize(mask, top, bottom).convert("RGBA")


def _rounded_mask(size: tuple[int, int], radius: float) -> Image.Image:
    """4 倍超采样画圆角遮罩，缩回目标尺寸后边缘更干净。"""
    width, height = size
    scale = 4
    mask = Image.new("L", (width * scale, height * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=max(0, round(radius * scale)),
        fill=255,
    )
    return mask.resize(size, Image.Resampling.LANCZOS)


def _drop_shadow(
    base: Image.Image,
    box: tuple[int, int, int, int],
    radius: float,
    color: Color,
    alpha: int,
    blur: float,
    offset: tuple[int, int],
) -> None:
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (box[0] + offset[0], box[1] + offset[1], box[2] + offset[0], box[3] + offset[1]),
        radius=radius,
        fill=alpha,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(Image.new("RGBA", base.size, color + (255,)), (0, 0), mask)
    base.alpha_composite(layer)


def _star(draw: ImageDraw.ImageDraw, center_x: float, center_y: float, radius: float, fill: tuple[int, ...]) -> None:
    waist = radius * 0.3
    points = [
        (center_x, center_y - radius),
        (center_x + waist, center_y - waist),
        (center_x + radius, center_y),
        (center_x + waist, center_y + waist),
        (center_x, center_y + radius),
        (center_x - waist, center_y + waist),
        (center_x - radius, center_y),
        (center_x - waist, center_y - waist),
    ]
    draw.polygon(points, fill=fill)


def _gradient_text(text: str, size: int, top: Color, bottom: Color, stroke: int = 2) -> Image.Image:
    font = _font(size)
    bbox = font.getbbox(text, stroke_width=stroke)
    pad = 4
    width = bbox[2] - bbox[0] + pad * 2
    height = bbox[3] - bbox[1] + pad * 2
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).text(
        (pad - bbox[0], pad - bbox[1]),
        text,
        font=font,
        fill=255,
        stroke_width=stroke,
        stroke_fill=255,
    )
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(_linear_gradient((width, height), top, bottom), (0, 0), mask)
    layer.putalpha(mask)
    return layer


def _wrap_phrase(text: str, size: int, max_width: float, max_lines: int = 3) -> list[str]:
    """按像素宽度折行，优先在标点后断开，避免最后一行只剩一两个字。"""
    font = _font(size)
    lines: list[str] = []
    rest = text.strip()
    while rest and len(lines) < max_lines:
        cut = 0
        while cut < len(rest) and font.getlength(rest[: cut + 1]) <= max_width:
            cut += 1
        if cut >= len(rest):
            lines.append(rest)
            rest = ""
            break
        if cut == 0:  # 单个字符就超宽（理论上不会发生），硬切一个防止死循环
            cut = 1
        # 若剩下的文字下一行还放得下，就在本行内最后一个逗号/句号后断开；
        # 这样「今天幸运值拉满，」不会和后面的半句话挤在一起。
        punctuation_break = 0
        for index in range(1, cut):
            if rest[index - 1] in _BREAK_AFTER and font.getlength(rest[:index]) >= max_width * 0.32:
                punctuation_break = index
        if punctuation_break and font.getlength(rest[punctuation_break:]) <= max_width:
            lines.append(rest[:punctuation_break])
            rest = rest[punctuation_break:]
            continue
        # 普通断行：别让标点落在下一行行首
        while cut > 1 and rest[cut] in _NO_LINE_START:
            cut -= 1
        lines.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        # 超过最大行数，把剩余文字接到最后一行并省略
        tail = lines[-1] + rest
        while tail and font.getlength(tail + "…") > max_width:
            tail = tail[:-1]
        lines[-1] = tail + "…"
    return lines or [""]


# ---------------------------------------------------------------------------
# 主绘制
# ---------------------------------------------------------------------------
def render_card_image(luck_value: int, key: str, texts: CardTexts, date_text: str) -> bytes:
    """同步绘制人品卡并编码为 PNG。"""
    illustration_key = get_illustration_key(luck_value)
    palette = _PALETTES.get(illustration_key, _PALETTES[key])
    base = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 255))
    base.alpha_composite(
        _linear_gradient(
            (CARD_WIDTH, CARD_HEIGHT),
            _mix(palette.tint, _WHITE, 0.65),
            _mix(palette.soft, _WHITE, 0.80),
        )
    )

    # 卡片底色先按圆角裁好再贴到外背景上
    card = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    card.paste(
        _linear_gradient(
            (CARD_BOX[2] - CARD_BOX[0], CARD_BOX[3] - CARD_BOX[1]),
            _mix(palette.soft, _WHITE, 0.62),
            palette.tint,
        ),
        (CARD_BOX[0], CARD_BOX[1]),
    )
    card.putalpha(ImageChops.multiply(card.getchannel("A"), _rounded_mask((CARD_WIDTH, CARD_HEIGHT), CARD_RADIUS)))

    _drop_shadow(base, CARD_BOX, CARD_RADIUS, (0x5A, 0x48, 0x78), 42, 22, (0, 9))
    base.alpha_composite(card)

    border = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(CARD_BOX, radius=CARD_RADIUS, outline=(255, 255, 255, 220), width=1)
    base.alpha_composite(border)

    draw = ImageDraw.Draw(base)
    left = 72

    # 标题
    draw.text((left, 76), texts.title, font=_font(20), fill=palette.deep + (255,), anchor="ls")

    # 大数字：按墨迹包围盒（而不是字体排版框）贴到 (left, number_top)，
    # 否则数字两侧的侧边距会让它比标题向右缩进几个像素。
    number = str(luck_value)
    layer = _gradient_text(number, 178, palette.deep, palette.accent, stroke=2)
    number_top = 140
    number_ink = layer.getbbox() or (0, 0, 0, 0)
    base.alpha_composite(layer, (left - number_ink[0], number_top - number_ink[1]))
    number_width = number_ink[2] - number_ink[0]
    number_height = number_ink[3] - number_ink[1]

    # 单位：超过 100 时显示 MAX，避免 150 / 100 的歧义；底边与数字对齐
    unit = texts.unit_max if luck_value > _MAX_LUCK else texts.unit
    draw.text(
        (left + number_width + 16, number_top + number_height), unit, font=_font(30), fill=_MUTED + (255,), anchor="ls"
    )

    # 运势胶囊
    pill_font = _font(32)
    pill_x, pill_y, pill_height = left, 330, 58
    pill_width = 24 + 16 + 12 + pill_font.getlength(texts.fortune) + 24
    pill = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle(
        (pill_x, pill_y, pill_x + pill_width, pill_y + pill_height),
        radius=pill_height / 2,
        fill=palette.tint + (255,),
        outline=palette.accent + (160,),
        width=1,
    )
    base.alpha_composite(pill)
    _star(draw, pill_x + 32, pill_y + pill_height / 2, 8, palette.accent + (255,))
    draw.text(
        (pill_x + 52, pill_y + pill_height / 2),
        texts.fortune,
        font=pill_font,
        fill=palette.deep + (255,),
        anchor="lm",
    )

    # 那一句话
    phrase_font = _font(26)
    lines = _wrap_phrase(texts.phrase, 26, 486, max_lines=2)
    baseline = 432
    for line in lines:
        draw.text((left, baseline), line, font=phrase_font, fill=_BODY + (255,), anchor="ls")
        baseline += 38

    # 细分割线 + 底部日期
    divider = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(divider).rounded_rectangle((left, 495, left + 96, 497), radius=1, fill=palette.accent + (90,))
    base.alpha_composite(divider)
    footer_font = _font(18)
    draw.text((left, 522), date_text, font=footer_font, fill=_MUTED + (255,), anchor="ls")
    draw.text(
        (left + footer_font.getlength(date_text) + 14, 522),
        "·  JRRP",
        font=footer_font,
        fill=palette.deep + (255,),
        anchor="ls",
    )

    # 插画（原图自带圆角，裁切时已去掉白边并做圆角透明化，这里再套一层圆角遮罩）
    illustration = Image.open(_static_file(*_ILLUSTRATION_DIR, f"{illustration_key}.png")).convert("RGBA")
    illustration_height = 500
    illustration_width = (
        min(280, round(illustration_height * illustration.width / illustration.height))
        if illustration.width / illustration.height > 0.52
        else 253
    )
    illustration = ImageOps.fit(illustration, (illustration_width, illustration_height), Image.Resampling.LANCZOS)
    illustration_x = CARD_BOX[2] - 32 - illustration_width
    illustration_y = 40
    # 插画不套边框也不做投影，直接以自身圆角贴在卡片上
    mask = _rounded_mask((illustration_width, illustration_height), 24)
    illustration.putalpha(ImageChops.multiply(illustration.getchannel("A"), mask))
    base.alpha_composite(illustration, (illustration_x, illustration_y))

    buffer = io.BytesIO()
    base.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
