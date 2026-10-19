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
"""帮助面板渲染引擎（设计稿：moonlark-help-panel/DESIGN.md 方案 A）。

用 Pillow 直接绘制整张帮助图：几何常量、字号阶梯、灌栏算法与
moonlark-help-panel/build_demo.py 的 demo 一致，输出 2× 超采样折半后的 WebP。
"""

from __future__ import annotations

import asyncio
import io
import math
import time
import traceback
from itertools import pairwise
from operator import itemgetter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFont
from nonebot.log import logger

SCALE = 2

Color = tuple[int, int, int]

# --------------------------------------------------------------------------
# 素材路径
# --------------------------------------------------------------------------
_STATIC_ROOTS = [Path("src/static"), Path(__file__).resolve().parents[2].joinpath("static")]
FONT_PATH = "SarasaGothicSC-Regular.ttf"
LOGO_PATH = "help_panel_logo.png"


def _resolve(name: str) -> Optional[Path]:
    for root in _STATIC_ROOTS:
        if root.is_dir() and root.joinpath(name).is_file():
            return root.joinpath(name)
    return None


def font_available() -> bool:
    return _resolve(FONT_PATH) is not None


def logo_available() -> bool:
    return _resolve(LOGO_PATH) is not None


# --------------------------------------------------------------------------
# 调色板：二次元 · 浅色
# --------------------------------------------------------------------------
BG_TOP = (0xFF, 0xF7, 0xFB)  # 樱粉白
BG_BOTTOM = (0xED, 0xF3, 0xFF)  # 天空白
SURFACE = (0xFF, 0xFF, 0xFF)
BORDER = (0xE7, 0xEA, 0xF6)
DIVIDER = (0xEE, 0xF1, 0xF9)
TITLE_C = (0x2B, 0x2D, 0x4F)
BODY_C = (0x4A, 0x4F, 0x6E)
MUTED = (0x98, 0xA0, 0xBC)
FAINT = (0xC3, 0xC9, 0xDE)
PINK = (0xFF, 0x8F, 0xB1)
PINK_DEEP = (0xD9, 0x55, 0x7F)
PINK_TINT = (0xFF, 0xE7, 0xF0)
BLUE = (0x7C, 0xC4, 0xFF)
BLUE_DEEP = (0x2A, 0x6B, 0xB8)
BLUE_TINT = (0xE3, 0xEF, 0xFF)
MINT = (0x6F, 0xD8, 0xAE)
VIOLET = (0xA7, 0x8B, 0xFA)
CHIP_BG = (0xF8, 0xFA, 0xFF)
SHADOW_C = (0x2B, 0x2D, 0x4F)

# 分类 -> (底色, 前景色, 强调色)
CAT_COLORS = {
    "game": ((0xFF, 0xE7, 0xF0), (0xC0, 0x40, 0x6E), PINK),
    "tools": (BLUE_TINT, BLUE_DEEP, BLUE),
    "setting": ((0xED, 0xE8, 0xFF), (0x64, 0x46, 0xC4), VIOLET),
    "community": ((0xDF, 0xF6, 0xEC), (0x1E, 0x8A, 0x63), MINT),
    "new": ((0xFF, 0xF1, 0xDA), (0xB4, 0x76, 0x2A), (0xF6, 0xC4, 0x53)),
    "superuser": ((0xEC, 0xEE, 0xF6), (0x5A, 0x61, 0x80), MUTED),
}
CAT_ORDER_HINT = ["game", "tools", "setting", "community", "new"]

# 奖牌色 -> (主色, 卡片底色)
MEDALS = [
    ((0xE8, 0xA7, 0x2B), (0xFF, 0xF7, 0xE4)),
    ((0x8D, 0x9B, 0xBD), (0xED, 0xF1, 0xFA)),
    ((0xCE, 0x8B, 0x5A), (0xFD, 0xF1, 0xE7)),
]

# --------------------------------------------------------------------------
# 几何常量（逻辑像素；输出统一 2x 超采样后折半）
# --------------------------------------------------------------------------
PAD = 36
COL_W = 480  # 单栏宽度：固定值，这是移动端可读性的关键
GUTTER = 36
COLS = 2  # 方案 A 默认两栏
HEADER_H = 208
HOT_H = 158
FOOTER_H = 56
ROW_H = 34  # 行高恒定
NAME_W = 132  # 指令名泳道固定宽，保证说明文字左边界对齐
NAME_GAP = 14
CAT_H = 42
DESC_W = COL_W - NAME_W - NAME_GAP  # 334px
DESC_LADDER = (17, 15, 13)  # 说明文字的字号阶梯
NAME_LADDER = (15, 13)
LOGO_RATIO = 1264 / 848  # 3:2，LOGO 预留位
LOGO_H = 168
W = 2 * PAD + COLS * COL_W + (COLS - 1) * GUTTER  # 1068


# --------------------------------------------------------------------------
# 字体度量
# --------------------------------------------------------------------------
@lru_cache
def _font(size: int) -> ImageFont.FreeTypeFont:
    path = _resolve(FONT_PATH)
    if path is None:
        raise FileNotFoundError(f"帮助面板字体缺失: {FONT_PATH}")
    return ImageFont.truetype(str(path), size * SCALE)


def text_width(text: str, size: int) -> float:
    return _font(size).getlength(text) / SCALE


def fit_text(text: str, ladder: tuple[int, ...], limit: float) -> tuple[str, int, bool]:
    """把 text 塞进 limit 宽度：先降字号，仍超出才省略号。

    返回 (最终文本, 最终字号, 是否被截断)。
    """
    for size in ladder:
        if text_width(text, size) <= limit:
            return text, size, False
    size = ladder[-1]
    ell = "…"
    while text and text_width(text + ell, size) > limit:
        text = text[:-1]
    return text + ell, size, True


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------
@dataclass
class Cmd:
    name: str
    desc: str
    cat: str


@dataclass
class Piece:
    cat: str
    rows: list[Cmd]
    cont: bool = False


@dataclass
class Block:
    cat: str
    rows: list[Cmd] = field(default_factory=list)

    @property
    def height(self) -> float:
        return CAT_H + len(self.rows) * ROW_H


@dataclass
class PanelTexts:
    title: str
    eyebrow: str
    subtitle: str
    hint: str
    badge: str  # 「条指令」
    hot_title: str
    hot_note: str
    hot_count: str  # 「{} 次」
    row_count: str  # 「{} 条」
    cont: str  # 「‹{}›（续）」
    footer: str
    logo_alt: str
    logo_alt_sub: str
    cat_names: dict[str, str] = field(default_factory=dict)


def build_category_blocks(commands: list[Cmd]) -> list[Block]:
    """分类顺序：沿用现有 get_templates 的「首次出现」顺序，再按固定优先级收尾。"""
    order: list[str] = []
    for c in commands:
        if c.cat not in order:
            order.append(c.cat)
    first_seen = {cat: i for i, cat in enumerate(order)}
    order.sort(key=lambda k: (CAT_ORDER_HINT.index(k) if k in CAT_ORDER_HINT else 99, first_seen[k]))
    return [Block(cat, [c for c in commands if c.cat == cat]) for cat in order]


def pack_columns(blocks: list[Block], cols: int) -> list[list[Piece]]:
    """把分类块按顺序灌进各栏。栏内按顺序填到 target 高度为止，放不下的
    分类允许跨栏续排（带「(续)」小标），这样两栏高度差不超过一行，
    不会出现「左栏很长、右栏空一半」的报纸式空洞。"""
    total = sum(b.height for b in blocks)
    target = total / cols
    columns: list[list[Piece]] = [[] for _ in range(cols)]

    def col_height(i: int) -> float:
        return sum(CAT_H + len(p.rows) * ROW_H for p in columns[i])

    ci = 0
    for b in blocks:
        rows = list(b.rows)
        placed = False
        while rows:
            if ci >= cols - 1:
                ci = cols - 1
                take = len(rows)
            else:
                room = target - col_height(ci) - CAT_H
                take = len(rows) if room >= len(rows) * ROW_H else max(0, int(room // ROW_H))
                if take == 0 and not columns[ci]:
                    take = len(rows)  # 空栏必须至少落一个分类，防止死循环
            piece_rows, rows = rows[:take], rows[take:]
            if piece_rows:
                columns[ci].append(Piece(b.cat, piece_rows, cont=placed))
                placed = True
            if rows:
                ci += 1
    return columns


def apply_hot_data(
    rows: list[Cmd],
    hot_raw: list[tuple[str, int]],
) -> tuple[list[Cmd], list[tuple[str, int]], dict[str, Cmd]]:
    """热门去重：只保留仍在帮助列表里的指令，并从下方列表中剔除前三名。"""
    by_name = {c.name: c for c in rows}
    hot = [(n, cnt) for n, cnt in hot_raw if n in by_name][:3]
    hot_names = {n for n, _ in hot}
    shown = [c for c in rows if c.name not in hot_names]
    return shown, hot, by_name


# --------------------------------------------------------------------------
# 画布
# --------------------------------------------------------------------------
class Canvas:
    """逻辑坐标 → 2× 设备坐标。

    所有元素画在按各自包围盒裁剪的透明小图层上，再 alpha_composite 回底图，
    这样半透明填充不会覆盖已有像素（ImageDraw 直接往 RGBA 上写会整块替换）。
    """

    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (int(w * SCALE), int(h * SCALE)), (0, 0, 0, 255))

    def px(self, v: float) -> int:
        return round(v * SCALE)

    def text_width(self, text: str, size: int) -> float:
        return text_width(text, size)

    def stamp(self, x: float, y: float, layer: Image.Image) -> None:
        self.img.alpha_composite(layer, (max(0, self.px(x)), max(0, self.px(y))))

    # ---- 渐变 -----------------------------------------------------------
    def _linear_gradient(
        self,
        w: int,
        h: int,
        c0: Color,
        c1: Color,
        p0: tuple[float, float] = (0.0, 0.0),
        p1: tuple[float, float] = (0.6, 1.0),
        alpha: int = 255,
    ) -> Image.Image:
        """objectBoundingBox 意义上的线性渐变（设计稿 #bg / #accent 的等价物）。

        RGB 通道低分辨率生成后放大、alpha 在完整分辨率的纯色图上注入，
        避免 Pillow 对低 alpha RGBA 做 resize 时的预乘噪声。
        """
        gw, gh = max(8, min(w, 256)), max(8, min(h, 256))
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        denom = dx * dx + dy * dy if (dx or dy) else 1.0
        g = Image.new("RGB", (gw, gh))
        pixels = []
        for gy in range(gh):
            fy = (gy + 0.5) / gh
            for gx in range(gw):
                fx = (gx + 0.5) / gw
                t = min(1.0, max(0.0, ((fx - p0[0]) * dx + (fy - p0[1]) * dy) / denom))
                pixels.append(tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)))
        g.putdata(pixels)
        rgb = g.resize((w, h), Image.BICUBIC).convert("RGBA")
        rgb.putalpha(Image.new("L", rgb.size, min(255, alpha)))
        return rgb

    def _radial_gradient(self, w: int, h: int, color: Color, max_opacity: float) -> Image.Image:
        """柔和的径向光斑：RGB 纯色全分辨率，alpha 频道单独低分辨率生成再放大。"""
        gw, gh = max(8, min(w, 128)), max(8, min(h, 128))
        cx, cy = gw / 2, gh / 2
        r = max(gw, gh) / 2
        a = Image.new("L", (gw, gh))
        pixels = []
        for gy in range(gh):
            fy = gy + 0.5
            for gx in range(gw):
                t = min(1.0, math.hypot(gx + 0.5 - cx, fy - cy) / r)
                pixels.append(max(0, int(255 * max_opacity * (1 - t) ** 1.6)))
        a.putdata(pixels)
        img = Image.new("RGBA", (max(w, 1), max(h, 1)), (*color, 255))
        img.putalpha(a.resize(img.size, Image.BICUBIC))
        return img

    def _resolve_fill(
        self,
        fill: Color | str | None,
        w: int,
        h: int,
        alpha: int,
    ) -> tuple[Optional[Image.Image], Optional[tuple]]:
        """填充给到渐变串时返回 (渐变图层, None)；给到颜色时返回 (None, 带 alpha 颜色)。"""
        if fill is None:
            return None, None
        if fill == "bg":
            return self._linear_gradient(w, h, BG_TOP, BG_BOTTOM, (0, 0), (0.6, 1), alpha), None
        if fill == "accent":
            return self._linear_gradient(w, h, PINK, BLUE, (0, 0), (1, 0), alpha), None
        if fill == "grad_pink":
            return self._radial_gradient(w, h, PINK, 0.22 * alpha / 255), None
        if fill == "grad_blue":
            return self._radial_gradient(w, h, BLUE, 0.22 * alpha / 255), None
        if fill == "grad_mint":
            return self._radial_gradient(w, h, MINT, 0.18 * alpha / 255), None
        if isinstance(fill, tuple):
            return None, (*fill, alpha)
        return None, None

    # ---- 形状 -----------------------------------------------------------
    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: Color | str | None = None,
        rx: float = 0,
        stroke: Color | None = None,
        sw: float = 1,
        opacity: Optional[float] = None,
    ) -> None:
        dw, dh = self.px(w), self.px(h)
        lw = max(1, self.px(sw))
        pad = (lw + 2) if stroke else 0
        layer = Image.new("RGBA", (dw + pad * 2, dh + pad * 2), (0, 0, 0, 0))
        alpha = 255 if opacity is None else max(1, round(255 * opacity))
        grad, color = self._resolve_fill(fill, dw, dh, alpha)
        draw = ImageDraw.Draw(layer)
        if grad is not None:
            if rx > 0:
                shape = Image.new("L", layer.size, 0)
                ImageDraw.Draw(shape).rounded_rectangle(
                    [pad, pad, pad + dw - 1, pad + dh - 1],
                    radius=self.px(rx),
                    fill=alpha,
                )
            else:
                shape = Image.new("L", layer.size, alpha)
            full_alpha = Image.new("L", layer.size, 0)
            full_alpha.paste(grad.getchannel("A"), (pad, pad))
            layer.paste(grad, (pad, pad))
            layer.putalpha(ImageChops.multiply(full_alpha, shape))
        if color is not None:
            draw.rounded_rectangle([pad, pad, pad + dw - 1, pad + dh - 1], radius=self.px(rx), fill=color)
        if stroke is not None:
            draw.rounded_rectangle([pad, pad, pad + dw - 1, pad + dh - 1], radius=self.px(rx), outline=stroke, width=lw)
        self.stamp(x - pad / SCALE, y - pad / SCALE, layer)

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        fill: Color | str | None = None,
        stroke: Color | None = None,
        sw: float = 1.0,
        opacity: Optional[float] = None,
    ) -> None:
        d = self.px(2 * r)
        pad = (max(1, self.px(sw)) + 2) if stroke else 2
        layer = Image.new("RGBA", (d + pad * 2, d + pad * 2), (0, 0, 0, 0))
        alpha = 255 if opacity is None else max(1, round(255 * opacity))
        grad, color = self._resolve_fill(fill, d, d, alpha)
        shape = Image.new("L", layer.size, 0)
        ImageDraw.Draw(shape).ellipse([pad, pad, pad + d - 1, pad + d - 1], fill=alpha)
        if grad is not None:
            full_alpha = Image.new("L", layer.size, 0)
            full_alpha.paste(grad.getchannel("A"), (pad, pad))
            layer.paste(grad, (pad, pad))
            layer.putalpha(ImageChops.multiply(full_alpha, shape))
        draw = ImageDraw.Draw(layer)
        if color is not None:
            draw.ellipse([pad, pad, pad + d - 1, pad + d - 1], fill=color)
        if stroke is not None:
            draw.ellipse([pad, pad, pad + d - 1, pad + d - 1], outline=stroke, width=max(1, self.px(sw)))
        self.stamp(cx - r - pad / SCALE, cy - r - pad / SCALE, layer)

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: Color, sw: float = 1) -> None:
        ax, ay, bx, by = self.px(x1), self.px(y1), self.px(x2), self.px(y2)
        lw = max(1, self.px(sw))
        pad = lw + 1
        layer = Image.new("RGBA", (abs(bx - ax) + pad * 2, abs(by - ay) + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(layer).line(
            [(ax - min(ax, bx) + pad, ay - min(ay, by) + pad), (bx - min(ax, bx) + pad, by - min(ay, by) + pad)],
            fill=stroke,
            width=lw,
        )
        self.stamp(x1 - pad / SCALE, y1 - pad / SCALE, layer)

    # ---- 文本 -----------------------------------------------------------
    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: int,
        fill: Color,
        weight: int = 400,
        anchor: str = "start",
        opacity: Optional[float] = None,
        spacing: Optional[float] = None,
    ) -> float:
        """x/y 是基线坐标（与设计稿 SVG 一致）。返回该行在当前字号下的总宽（不含尾部 spacing）。"""
        if not s:
            return 0.0
        f = _font(size)
        h_anchor = {"start": "l", "middle": "m", "end": "r"}[anchor]
        stroke_w = 2 if weight >= 600 else 0
        alpha = 255 if opacity is None else max(1, round(255 * opacity))
        color = (*fill, alpha)
        tw = self.text_width(s, size)
        if spacing is not None:
            # letter-spacing：逐字符绘制
            dev_tw = self.px(tw) + self.px(spacing) * max(0, len(s) - 1)
            ascent, descent = f.getmetrics()
            head = stroke_w + 4
            layer = Image.new("RGBA", (dev_tw + head * 2, (ascent + descent) + stroke_w * 2 + 8), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            cx_dev, base_dev = head, ascent + stroke_w + 4
            for ch in s:
                if ch != " ":
                    d.text(
                        (cx_dev, base_dev),
                        ch,
                        font=f,
                        fill=color,
                        anchor=f"{h_anchor}s",
                        stroke_width=stroke_w,
                        stroke_fill=color,
                    )
                cx_dev += f.getlength(ch) + self.px(spacing)
            tw_sp = tw + spacing * max(0, len(s) - 1) / SCALE
            left_x = {"start": x, "middle": x - tw_sp / 2, "end": x - tw_sp}[anchor]
            self.stamp(left_x - head / SCALE, y - base_dev / SCALE, layer)
            return tw
        if opacity is not None and opacity < 1:
            ascent, descent = f.getmetrics()
            lw_dev = self.px(tw)
            head = stroke_w + 4
            layer = Image.new("RGBA", (lw_dev + head * 2, (ascent + descent) + stroke_w * 2 + 8), (0, 0, 0, 0))
            local_x = {"l": head, "m": head + lw_dev / 2, "r": head + lw_dev}[h_anchor]
            ImageDraw.Draw(layer).text(
                (local_x, ascent + stroke_w + 4),
                s,
                font=f,
                fill=color,
                anchor=f"{h_anchor}s",
                stroke_width=stroke_w,
                stroke_fill=color,
            )
            self.stamp(x - head / SCALE, y - (ascent + stroke_w + 4) / SCALE, layer)
            return tw
        ImageDraw.Draw(self.img).text(
            (self.px(x), self.px(y)),
            s,
            font=f,
            fill=color,
            anchor=f"{h_anchor}s",
            stroke_width=stroke_w,
            stroke_fill=color,
        )
        return tw

    # ---- 贴图 -----------------------------------------------------------
    def paste_image(self, x: float, y: float, image: Image.Image, radius: float = 0) -> None:
        """把 RGBA 图贴到 (x, y)，可选圆角裁切（与图片自身 alpha 相乘）。"""
        img = image
        if radius:
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, img.width - 1, img.height - 1],
                radius=self.px(radius),
                fill=255,
            )
            if "A" in img.getbands():
                mask = ImageChops.multiply(mask, img.getchannel("A"))
            img = img.copy()
            img.putalpha(mask)
        self.img.alpha_composite(img, (self.px(x), self.px(y)))


# --------------------------------------------------------------------------
# 装饰形状（全部矢量绘制，不依赖 emoji 字体）
# --------------------------------------------------------------------------
def petal(canvas: Canvas, cx: float, cy: float, r: float, color: Color, opacity: float = 0.5, n: int = 5) -> None:
    """樱花瓣：n 个花瓣圆 + 花心，纯矢量。"""
    for i in range(n):
        a = 2 * math.pi * i / n - math.pi / 2
        canvas.circle(cx + r * 0.62 * math.cos(a), cy + r * 0.62 * math.sin(a), r * 0.42, color, opacity=opacity)
    canvas.circle(cx, cy, r * 0.24, PINK_DEEP, opacity=opacity * 0.9)


def sparkle(canvas: Canvas, cx: float, cy: float, r: float, color: Color, opacity: float = 0.55) -> None:
    k = r * 0.26
    pts = [
        (cx, cy - r),
        (cx + k, cy - k),
        (cx + r, cy),
        (cx + k, cy + k),
        (cx, cy + r),
        (cx - k, cy + k),
        (cx - r, cy),
        (cx - k, cy - k),
    ]
    layer = Image.new("RGBA", (canvas.px(2 * r) + 4, canvas.px(2 * r) + 4), (0, 0, 0, 0))
    ox, oy = canvas.px(cx - r) - 2, canvas.px(cy - r) - 2
    ImageDraw.Draw(layer).polygon(
        [(canvas.px(px) - ox, canvas.px(py) - oy) for px, py in pts],
        fill=(*color, max(1, int(255 * opacity))),
    )
    canvas.stamp(cx - r - 2 / SCALE, cy - r - 2 / SCALE, layer)


def _cubic_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    n: int,
) -> list[tuple[float, float]]:
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        out.append(
            (
                mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
                mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1],
            ),
        )
    return out


def flame(
    canvas: Canvas,
    cx: float,
    cy: float,
    s: float,
    color: Color,
    opacity: Optional[float] = None,
    inner: bool = False,
) -> None:
    """火焰：两段三次贝塞尔 + 底部半圆，与设计稿的 path 等价。"""

    def points() -> list[tuple[float, float]]:
        pts = _cubic_points(
            (cx, cy - s),
            (cx + s * 0.45, cy - s * 0.45),
            (cx + s * 0.8, cy - s * 0.1),
            (cx + s * 0.8, cy + s * 0.3),
            24,
        )[1:]
        c, r = (cx, cy + s * 0.3), s * 0.8
        for i in range(1, 25):
            t = math.pi * i / 24
            pts.append((c[0] + r * math.cos(t), c[1] + r * math.sin(t)))
        pts.extend(
            _cubic_points(
                (cx - s * 0.8, cy + s * 0.3),
                (cx - s * 0.8, cy - s * 0.1),
                (cx - s * 0.45, cy - s * 0.45),
                (cx, cy - s),
                24,
            )[1:],
        )
        return pts

    margin = (s * 1.0) / SCALE
    ox, oy = canvas.px(cx - s * 0.85) - 4, canvas.px(cy - s * 1.05) - 4
    layer = Image.new("RGBA", (int(canvas.px(s * 1.7)) + 8, int(canvas.px(s * 2.15)) + 8), (0, 0, 0, 0))
    alpha = 255 if opacity is None else max(1, int(255 * opacity))
    ImageDraw.Draw(layer).polygon(
        [(canvas.px(px) - ox, canvas.px(py) - oy) for px, py in points()],
        fill=(*color, alpha),
    )
    canvas.stamp(cx - s * 0.85 - 4 / SCALE, cy - s * 1.05 - 4 / SCALE, layer)
    if inner:
        flame(canvas, cx, cy + s * 0.18, s * 0.5, (0xFF, 0xFF, 0xFF), opacity=0.5)
    del margin


def crescent(canvas: Canvas, cx: float, cy: float, r: float, color: Color, cut: Color = (0xF8, 0xFA, 0xFF)) -> None:
    """月牙：实心圆 + 一枚底色圆「咬」掉右侧。"""
    canvas.circle(cx, cy, r, color)
    canvas.circle(cx + r * 0.52, cy - r * 0.22, r * 0.86, cut)


def shadow(canvas: Canvas, x: float, y: float, w: float, h: float, rx: float) -> None:
    """双层极淡投影：两层偏移圆角矩形。"""
    canvas.rect(x, y + 6, w, h, SHADOW_C, rx=rx + 2, opacity=0.035)
    canvas.rect(x, y + 2, w, h, SHADOW_C, rx=rx + 1, opacity=0.045)


def dashed_rounded_rect(
    canvas: Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    rx: float,
    stroke: Color,
    sw: float = 1.4,
    dash: float = 8,
    gap: float = 7,
) -> None:
    """虚线圆角矩形：沿参数化路径采样，交替画 dash 与 gap。"""
    step = 3.0
    x0, y0, x1, y1 = x, y, x + w, y + h
    pts: list[tuple[float, float]] = []

    def corner(pcx: float, pcy: float, a0: float, a1: float) -> None:
        n = max(2, math.ceil(abs(a1 - a0) * rx / step))
        pts.extend(
            (pcx + rx * math.cos(a0 + (a1 - a0) * k / n), pcy + rx * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)
        )

    pts.extend(((x0 + rx, y0), (x1 - rx, y0)))
    corner(x1 - rx, y0 + rx, -math.pi / 2, 0)
    pts.append((x1, y1 - rx))
    corner(x1 - rx, y1 - rx, 0, math.pi / 2)
    pts.append((x0 + rx, y1))
    corner(x0 + rx, y1 - rx, math.pi / 2, math.pi)
    pts.append((x0, y0 + rx))
    corner(x0 + rx, y0 + rx, math.pi, 3 * math.pi / 2)

    dist = 0.0
    for (ax, ay), (bx, by) in pairwise(pts):
        seg = math.hypot(bx - ax, by - ay)
        if seg == 0:
            continue
        pos = dist % (dash + gap)
        if pos < dash:
            t = min(seg, dash - pos) / seg
            canvas.line(ax, ay, ax + (bx - ax) * t, ay + (by - ay) * t, stroke, sw)
        dist += seg


# --------------------------------------------------------------------------
# 各版块绘制
# --------------------------------------------------------------------------
def draw_cat_header(canvas: Canvas, texts: PanelTexts, colx: float, y: float, col_w: float, piece: Piece) -> float:
    """分类头（或续排小标），返回消耗的高度。"""
    bg, fg, accent = CAT_COLORS.get(piece.cat, CAT_COLORS["new"])
    name = texts.cat_names.get(piece.cat, piece.cat)
    if piece.cont:
        canvas.text(colx + 2, y + 22, texts.cont.format(name), 13, MUTED, weight=600)
    else:
        canvas.rect(colx, y + 9, 5, 22, accent, rx=2.5)
        canvas.text(colx + 17, y + 22, name, 19, TITLE_C, weight=700)
        chip = texts.row_count.format(len(piece.rows))
        cw = text_width(chip, 12) + 22
        canvas.rect(colx + col_w - cw, y + 10, cw, 22, bg, rx=11)
        canvas.text(colx + col_w - cw / 2, y + 21, chip, 12, fg, weight=600, anchor="middle")
    canvas.line(colx, y + CAT_H - 7, colx + col_w, y + CAT_H - 7, DIVIDER, 1)
    return CAT_H


def draw_columns(
    canvas: Canvas,
    texts: PanelTexts,
    columns: list[list[Piece]],
    body_y: float,
    *,
    x0: float = PAD,
    col_w: float = COL_W,
    gutter: float = GUTTER,
    name_w: float = NAME_W,
    row_h: float = ROW_H,
) -> None:
    """指令列表（分栏）：方案 A / B / C 共用。"""
    desc_w = col_w - name_w - NAME_GAP
    for ci, col in enumerate(columns):
        colx = x0 + ci * (col_w + gutter)
        y = body_y
        for piece in col:
            bg, fg, _accent = CAT_COLORS.get(piece.cat, CAT_COLORS["new"])
            y += draw_cat_header(canvas, texts, colx, y, col_w, piece)
            for row in piece.rows:
                row_cy = y + row_h / 2
                ntext, nsize, _ = fit_text(row.name, NAME_LADDER, name_w - 20)
                nw = min(text_width(ntext, nsize) + 20, name_w)
                canvas.rect(colx, row_cy - 12, nw, 24, bg, rx=12)
                canvas.text(colx + nw / 2, row_cy, ntext, nsize, fg, weight=600, anchor="middle")
                dtext, dsize, _ = fit_text(row.desc, DESC_LADDER, desc_w)
                canvas.text(colx + name_w + NAME_GAP, row_cy, dtext, dsize, BODY_C)
                y += row_h


def draw_hot(
    canvas: Canvas,
    texts: PanelTexts,
    hot_y: float,
    hot: list[tuple[str, int]],
    by_name: dict[str, Cmd],
    card_x: float,
    card_w: float,
) -> None:
    """热门指令条带。"""
    shadow(canvas, card_x, hot_y, card_w, HOT_H, 24)
    canvas.rect(card_x, hot_y, card_w, HOT_H, SURFACE, rx=24, stroke=BORDER)
    canvas.rect(card_x, hot_y, 6, HOT_H, "accent", rx=3)
    flame(canvas, card_x + 40, hot_y + 36, 13, PINK, inner=True)
    canvas.text(card_x + 62, hot_y + 36, texts.hot_title, 21, TITLE_C, weight=700)
    canvas.text(card_x + card_w - 26, hot_y + 36, texts.hot_note, 13, MUTED, anchor="end")
    gap = 21
    hcard_w = (card_w - 52 - 2 * gap) / 3
    hcard_h = 86
    for i, (name, count) in enumerate(hot):
        cmd = by_name[name]
        medal, tint = MEDALS[i]
        cx = card_x + 26 + i * (hcard_w + gap)
        cy = hot_y + 56
        canvas.rect(cx, cy, hcard_w, hcard_h, tint, rx=16, stroke=medal, sw=1)
        canvas.circle(cx + 34, cy + 32, 19, medal, opacity=0.18)
        canvas.circle(cx + 34, cy + 32, 19, stroke=medal, sw=1.4)
        # 排名用裸数字：①-⑨ 小字号下圆圈套圆圈，辨识度不如裸数字
        canvas.text(cx + 34, cy + 32, str(i + 1), 20, medal, weight=700, anchor="middle")
        # 指令名：不加 pill 底色，靠字号 + 奖牌色 + 字重撑起主次
        ntext, nsize, _ = fit_text(name, (19, 17, 16), hcard_w - 150)
        name_w = text_width(ntext, nsize)
        canvas.text(cx + 62, cy + 32, ntext, nsize, medal, weight=600)
        canvas.text(cx + 62 + name_w + 13, cy + 33, texts.hot_count.format(f"{count:,}"), 12, MUTED)
        # 第二行：说明 + 右对齐的分类名
        dtext, dsize, _ = fit_text(cmd.desc, (13, 12), hcard_w - 116)
        canvas.text(cx + 16, cy + 62, dtext, dsize, BODY_C)
        cat_text = texts.cat_names.get(cmd.cat, cmd.cat)
        canvas.text(
            cx + hcard_w - 16,
            cy + 62,
            cat_text,
            11,
            CAT_COLORS.get(cmd.cat, CAT_COLORS["new"])[1],
            weight=600,
            anchor="end",
        )


def draw_footer(canvas: Canvas, texts: PanelTexts, footer_y: float, w: float = W) -> None:
    canvas.line(PAD, footer_y + 6, w - PAD, footer_y + 6, DIVIDER, 1)
    sparkle(canvas, PAD + 6, footer_y + 6, 5, PINK, opacity=0.7)
    sparkle(canvas, w - PAD - 6, footer_y + 6, 5, BLUE, opacity=0.7)
    canvas.text(w / 2, footer_y + 32, texts.footer, 13, MUTED, anchor="middle")


def draw_cover_logo(
    canvas: Canvas,
    texts: PanelTexts,
    card_x: float,
    card_w: float,
    cy: float,
    ch: float,
    total: int,
    logo: Optional[Image.Image],
) -> None:
    """方案 A 封面：标题组 + 指令总数 badge + LOGO。"""
    tx = card_x + 34
    eb_spacing = 1.4
    eb = texts.eyebrow
    # eyebrow 宽 = 逐字符宽度和 + 字距 + 两侧内边距（demo: text + 26 + 一枚字距）
    eb_tw = text_width(eb, 12) + eb_spacing * max(0, len(eb) - 1)
    eb_w = eb_tw + 26 + eb_spacing
    canvas.rect(tx, cy + 26, eb_w, 26, PINK_TINT, rx=13)
    canvas.text(tx + eb_w / 2, cy + 39, eb, 12, PINK_DEEP, weight=600, anchor="middle", spacing=eb_spacing)
    title_w = canvas.text(tx, cy + 100, texts.title, 40, TITLE_C, weight=700)
    sparkle(canvas, tx + title_w + 26, cy + 84, 11, PINK, opacity=0.85)
    canvas.text(tx, cy + 132, texts.subtitle, 15, MUTED)
    canvas.text(tx, cy + 164, texts.hint, 13, FAINT)

    logo_w = LOGO_H * LOGO_RATIO
    logo_x = card_x + card_w - 34 - logo_w
    logo_y = cy + (ch - LOGO_H) / 2
    chip_w, chip_h = 118, 70
    chip_x = logo_x - 26 - chip_w
    chip_y = cy + (ch - chip_h) / 2
    canvas.rect(chip_x, chip_y, chip_w, chip_h, CHIP_BG, rx=16, stroke=BORDER)
    canvas.text(chip_x + chip_w / 2, chip_y + 36, str(total), 26, TITLE_C, weight=700, anchor="middle")
    canvas.text(chip_x + chip_w / 2, chip_y + 56, texts.badge, 11, MUTED, anchor="middle")
    canvas.rect(chip_x + 27, chip_y + chip_h - 3, chip_w - 54, 3, "accent", rx=1.5)

    text_block_w = max(text_width(texts.title, 40), text_width(texts.subtitle, 15), text_width(texts.hint, 13))
    mid_x = (tx + text_block_w + chip_x) / 2
    petal(canvas, mid_x - 18, cy + 72, 12, PINK, opacity=0.34)
    sparkle(canvas, mid_x + 30, cy + 128, 8, BLUE, opacity=0.5)
    sparkle(canvas, mid_x - 32, cy + 152, 6, VIOLET, opacity=0.4)

    if logo is not None:
        # 落地放法（contain）：等比缩放 → 透明底居中 → 圆角 mask 裁切
        slot_w_dev, slot_h_dev = round(logo_w * SCALE), round(LOGO_H * SCALE)
        scale = min(slot_w_dev / logo.width, slot_h_dev / logo.height)
        resized = logo.resize((max(1, round(logo.width * scale)), max(1, round(logo.height * scale))), Image.LANCZOS)
        slot = Image.new("RGBA", (slot_w_dev, slot_h_dev), (0, 0, 0, 0))
        slot.paste(resized, ((slot.width - resized.width) // 2, (slot.height - resized.height) // 2))
        slot_w, slot_h = slot.width / SCALE, slot.height / SCALE
        canvas.paste_image(logo_x + (logo_w - slot_w) / 2, logo_y + (LOGO_H - slot_h) / 2, slot, radius=18)
    else:
        # 降级：设计稿里的虚线占位框
        canvas.rect(logo_x, logo_y, logo_w, LOGO_H, CHIP_BG, rx=18, opacity=0.6)
        dashed_rounded_rect(canvas, logo_x, logo_y, logo_w, LOGO_H, 18, FAINT, 1.4, 8, 7)
        crescent(canvas, logo_x + logo_w / 2 - 34, logo_y + LOGO_H / 2 - 14, 15, BLUE)
        sparkle(canvas, logo_x + logo_w / 2 + 4, logo_y + LOGO_H / 2 - 24, 9, PINK, opacity=0.9)
        canvas.circle(logo_x + logo_w / 2 + 34, logo_y + LOGO_H / 2 - 8, 6, MINT, opacity=0.85)
        canvas.text(
            logo_x + logo_w / 2,
            logo_y + LOGO_H / 2 + 30,
            texts.logo_alt,
            15,
            MUTED,
            weight=600,
            anchor="middle",
        )
        canvas.text(logo_x + logo_w / 2, logo_y + LOGO_H / 2 + 52, texts.logo_alt_sub, 12, FAINT, anchor="middle")


def draw_panel(
    rows: list[Cmd],
    hot: list[tuple[str, int]],
    texts: PanelTexts,
    logo: Optional[Image.Image],
) -> Image.Image:
    """整张面板（版面与 build_demo.py build() 一致），返回 2× 设备图。"""
    shown, hot, by_name = apply_hot_data(rows, hot)
    blocks = [b for b in build_category_blocks(shown) if b.rows]
    columns = pack_columns(blocks, COLS)
    content_h = max(sum(CAT_H + len(p.rows) * ROW_H for p in col) for col in columns)

    cover_y = PAD
    if hot:
        hot_y = cover_y + HEADER_H + 22
        body_y = hot_y + HOT_H + 26
    else:
        hot_y = None
        body_y = cover_y + HEADER_H + 26
    footer_y = body_y + content_h + 24
    canvas_h = footer_y + FOOTER_H

    canvas = Canvas(W, canvas_h)

    # 背景
    canvas.rect(0, 0, W, canvas_h, "bg")
    canvas.circle(W * 0.12, 90, 260, fill="grad_pink")
    canvas.circle(W * 0.94, 320, 300, fill="grad_blue")
    canvas.circle(W * 0.06, canvas_h - 160, 240, fill="grad_mint")
    canvas.circle(W * 0.88, canvas_h - 120, 260, fill="grad_pink")
    # 顶部渐变细带
    canvas.rect(0, 0, W, 4, "accent")

    card_x, card_w = PAD, W - 2 * PAD

    # 封面
    shadow(canvas, card_x, cover_y, card_w, HEADER_H, 28)
    canvas.rect(card_x, cover_y, card_w, HEADER_H, SURFACE, rx=28, stroke=BORDER)
    draw_cover_logo(canvas, texts, card_x, card_w, cover_y, HEADER_H, len(shown) + len(hot), logo)

    # 背景装饰：只落在卡片之外或留白区，绝不压字
    petal(canvas, PAD + 46, 46, 15, PINK, opacity=0.4)
    petal(canvas, W - PAD - 54, 30, 10, PINK, opacity=0.3)
    sparkle(canvas, W - PAD - 12, 62, 8, BLUE, opacity=0.5)
    sparkle(canvas, 16, 120, 6, VIOLET, opacity=0.35)
    petal(canvas, 22, canvas_h - 40, 11, PINK, opacity=0.3)
    sparkle(canvas, W - 22, canvas_h - 60, 9, BLUE, opacity=0.45)
    if hot_y is not None:
        sparkle(canvas, PAD + 24, hot_y + 26, 8, VIOLET, opacity=0.5)
        petal(canvas, card_x + 300, hot_y + 34, 11, PINK, opacity=0.38)

    # 热门指令 / 指令列表 / 页脚
    if hot:
        draw_hot(canvas, texts, hot_y, hot, by_name, card_x, card_w)
    draw_columns(canvas, texts, columns, body_y)
    draw_footer(canvas, texts, footer_y)

    return canvas.img


# --------------------------------------------------------------------------
# 热门指令 provider 注册表（larkhelp 不依赖 command_stats，启动时注入）
# --------------------------------------------------------------------------
_hot_provider: Optional[Callable[[], Awaitable[list]]] = None


def register_hot_provider(provider: Callable[[], Awaitable[list]]) -> None:
    """注册热门指令 provider（异步调用，返回 [{command, count}, ...]）。

    provider 未注册或抛错时，面板自动省略热门分区，而不是整个 help 报错。
    """
    global _hot_provider
    _hot_provider = provider
    logger.debug("nonebot_plugin_larkhelp: 已注册热门指令 provider")


async def _get_hot() -> list[tuple[str, int]]:
    if _hot_provider is None:
        return []
    try:
        rows = await asyncio.wait_for(_hot_provider(), 10)
    except Exception:
        logger.warning("nonebot_plugin_larkhelp: 获取热门指令失败\n" + traceback.format_exc())
        return []
    out = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("command"):
            continue
        try:
            out.append((str(row["command"]), int(row["count"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


# --------------------------------------------------------------------------
# 图像编码 / 降级素材
# --------------------------------------------------------------------------
def encode_panel(image: Image.Image) -> bytes:
    """2× 超采样图折半后编码为 PNG 字节（外层再转 WebP）。"""
    img = image.resize((image.width // SCALE, image.height // SCALE), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def load_logo() -> Optional[Image.Image]:
    path = _resolve(LOGO_PATH)
    if path is None:
        return None
    try:
        with Image.open(path) as img:
            return img.convert("RGBA")
    except Exception:
        logger.warning(f"帮助面板 LOGO 加载失败: {path}")
        return None


# --------------------------------------------------------------------------
# 渲染入口（内存缓存：lang × hot_sig，10 分钟 TTL）
# --------------------------------------------------------------------------
_PANEL_CACHE: dict[tuple[str, str], tuple[float, bytes]] = {}
_PANEL_CACHE_TTL = 600  # 10 分钟
_CACHE_MAX = 32


def cache_get(key: tuple[str, str]) -> Optional[bytes]:
    item = _PANEL_CACHE.get(key)
    if item is None:
        return None
    ts, data = item
    if time.time() - ts > _PANEL_CACHE_TTL:
        _PANEL_CACHE.pop(key, None)
        return None
    return data


def cache_set(key: tuple[str, str], data: bytes) -> None:
    now = time.time()
    for k, (ts, _) in list(_PANEL_CACHE.items()):
        if now - ts > _PANEL_CACHE_TTL:
            _PANEL_CACHE.pop(k, None)
    if len(_PANEL_CACHE) >= _CACHE_MAX:
        oldest = min(_PANEL_CACHE, key=lambda k: _PANEL_CACHE[k][0])
        _PANEL_CACHE.pop(oldest, None)
    _PANEL_CACHE[key] = (now, data)


async def _get_lang(user_id: str) -> str:
    from nonebot_plugin_larklang.__main__ import get_user_language
    from nonebot_plugin_orm import get_session

    session = get_session()
    try:
        return await get_user_language(str(user_id), session)
    finally:
        await session.close()


async def _lang_text(key: str, user_id: str, *args) -> str:
    from nonebot_plugin_larklang.__main__ import LangHelper

    return await LangHelper("larkhelp").text(key, user_id, *args)


async def _collect_texts(user_id: str) -> PanelTexts:
    import datetime

    return PanelTexts(
        title=await _lang_text("panel.title", user_id),
        eyebrow=await _lang_text("panel.eyebrow", user_id),
        subtitle=await _lang_text("panel.subtitle", user_id, datetime.datetime.now().astimezone().date().isoformat()),
        hint=await _lang_text("panel.hint", user_id),
        badge=await _lang_text("panel.badge", user_id),
        hot_title=await _lang_text("panel.hot_title", user_id),
        hot_note=await _lang_text("panel.hot_note", user_id),
        hot_count=await _lang_text("panel.hot_count", user_id),
        row_count=await _lang_text("panel.row_count", user_id),
        cont=await _lang_text("panel.cont", user_id),
        footer=await _lang_text("panel.footer", user_id),
        logo_alt=await _lang_text("panel.logo_alt", user_id),
        logo_alt_sub=await _lang_text("panel.logo_alt_sub", user_id),
    )


async def _collect_rows(user_id: str, help_list: dict) -> list[Cmd]:
    """从帮助列表构造绘制用行数据（按指令名排序，排除 superuser 分类）"""
    from nonebot_plugin_larklang.__main__ import LangHelper

    helper_cache: dict[str, LangHelper] = {}
    rows = []
    for name, data in sorted(help_list.items(), key=itemgetter(0)):
        if data.category == "superuser":
            continue
        helper = helper_cache.setdefault(data.plugin, LangHelper(data.plugin))
        rows.append(Cmd(name, await helper.text(data.description, user_id), data.category))
    return rows


async def render_help_panel(user_id: str, help_list: dict) -> bytes:
    """渲染帮助面板（方案 A），返回 WebP 字节。

    help_list 是 larkhelp 主模块维护的 {指令名: CommandHelp} 映射；
    superuser 分类不参与渲染，热门前三名会从列表里移出。
    数据（描述、热门榜）就绪后整图绘制在线程池里完成，不阻塞事件循环。
    """
    if not help_list:
        raise ValueError("No Command")
    if not font_available():
        raise RuntimeError("帮助面板字体缺失，回退 HTML 渲染")

    texts = await _collect_texts(user_id)
    rows = await _collect_rows(user_id, help_list)
    if not rows:
        raise ValueError("No Command")

    hot_raw = await _get_hot()
    row_names = {c.name for c in rows}
    hot = [(n, cnt) for n, cnt in hot_raw if n in row_names][:3]
    category_of = {name: data.category for name, data in help_list.items()}
    for cat in {c.cat for c in rows} | {category_of[name] for name, _ in hot}:
        texts.cat_names.setdefault(cat, await _lang_text(f"list.category.{cat}", user_id))

    lang_key = await _get_lang(user_id)
    key = (lang_key, "|".join(f"{n}:{c}" for n, c in hot))
    if cached := cache_get(key):
        return cached

    logo = load_logo()
    loop = asyncio.get_running_loop()
    image = await loop.run_in_executor(None, draw_panel, rows, hot, texts, logo)
    data = to_webp(image)
    cache_set(key, data)
    return data


def to_webp(image: Image.Image) -> bytes:
    """折半 + 转 WebP（沿用 nonebot_plugin_render 的编码参数）。"""
    from nonebot_plugin_render.render import convert_image_to_webp

    return convert_image_to_webp(encode_panel(image))
