"""``.wakeuprank today`` 时间轴的回归测试。

背景：``today`` 原本复用 ``nonebot_plugin_ranking.generate_image`` 的排行榜卡片，把当天
早起的人按时间先后编成「第 1、2、3……名」。但 ``today`` 要表达的是「今天每个人几点起的」，
名次只是时间先后的副产品，排行榜卡片反而把注意力从时刻挪到了名次上。这一版改成时间轴：
横轴是 4:00-14:00 的起床窗口，每人一行，圆点落在自己今天第一次出现的位置上。

这里钉住三件事：位置换算（含越界钳制）、时间轴点由排名字段构建、模板输出的是时间轴而
不是名次列表。模板渲染使用与 ``nonebot_plugin_render.render`` 相同的 Jinja 环境配置，
纯模板渲染、不需要浏览器。
"""

from pathlib import Path
from typing import Any, TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from nonebot_plugin_ranking.types import RankingData

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "src" / "templates"
_TEMPLATE_NAME = "wakeuprank_timeline.html.jinja"
_AXIS_TEXTS = ["04:00", "06:00", "08:00", "10:00", "12:00", "14:00"]
_AXIS_TICKS = [
    {"text": "04:00", "percent": 0.0, "align": "start"},
    {"text": "06:00", "percent": 20.0, "align": "center"},
    {"text": "08:00", "percent": 40.0, "align": "center"},
    {"text": "10:00", "percent": 60.0, "align": "center"},
    {"text": "12:00", "percent": 80.0, "align": "center"},
    {"text": "14:00", "percent": 100.0, "align": "end"},
]


def _points() -> list[dict[str, Any]]:
    return [
        {"user_id": "1", "nickname": "XiaoDeng3386", "time": "04:07:12", "percent": 1.2, "is_me": True},
        {"user_id": "2", "nickname": "StarWorld", "time": "06:31:09", "percent": 25.19, "is_me": False},
        {"user_id": "3", "nickname": "yukino", "time": "13:57:44", "percent": 99.62, "is_me": False},
    ]


def _render(*, points: list[dict[str, Any]] | None = None, has_me: bool | None = None, **overrides: Any) -> str:
    points = _points() if points is None else points
    context: dict[str, Any] = {
        "base": "base/default.html.jinja",
        "main_title": "今日起床时间轴",
        "footer": "由 Moonlark 生成",
        "background_url": "",
        "points": points,
        "axis_ticks": _AXIS_TICKS,
        "has_me": any(point["is_me"] for point in points) if has_me is None else has_me,
        "count_label": f"今日共 {len(points)} 人早起",
        "me_label": "我",
    }
    context.update(overrides)
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env.get_template(_TEMPLATE_NAME).render(**context)


def test_timeline_draws_one_track_per_user() -> None:
    """每个人一行，圆点按百分比落在轨道上，位置用 clamp 限制在轨道内"""
    html = _render()

    # 三行，其中调用者那一行额外带 tl-row-me（容器 <div class="tl-rows"> 不算行）
    assert html.count('<div class="tl-row">') == 2
    assert html.count('<div class="tl-row tl-row-me">') == 1
    assert html.count('<span class="tl-track">') == 3
    assert html.count('<span class="tl-marker"') == 3
    # 圆点位置来自 percent，并用 clamp 保证贴边的点不会画到轨道外
    assert "left: clamp(5px, 1.2%, calc(100% - 5px))" in html
    assert "left: clamp(5px, 99.62%, calc(100% - 5px))" in html


def test_timeline_has_no_rank_numbering() -> None:
    """不再输出「1. xxx」这种名次前缀，也不再用排行榜卡片的类名"""
    html = _render()

    for index in range(1, 4):
        assert f"{index}. " not in html
    assert "card-body ranking" not in html
    assert 'class="num"' not in html


def test_timeline_renders_axis_and_summary() -> None:
    """横轴刻度、刻度竖线、人数摘要都要渲染出来"""
    html = _render()

    for text in _AXIS_TEXTS:
        assert f">{text}</span>" in html
    # 首尾标签贴住轨道两端、中间标签居中，避免标签整体偏移到刻度线右边
    assert 'class="tl-axis-label tl-axis-start" style="left: 0.0%"' in html
    assert 'class="tl-axis-label tl-axis-end" style="left: 100.0%"' in html
    assert html.count('class="tl-axis-label tl-axis-center"') == 4
    # 每行轨道内都画了中间刻度线（首尾由轨道左右边框表示）
    assert html.count('<span class="tl-tick" style="left: 20.0%"></span>') == 3
    assert "今日共 3 人早起" in html
    assert "04:07:12" in html
    assert "13:57:44" in html
    for nickname in ("XiaoDeng3386", "StarWorld", "yukino"):
        assert nickname in html


def test_timeline_highlights_caller() -> None:
    """调用者那一行加高亮类，图例显示「我」；调用者不在列表里时不显示图例"""
    html = _render()
    assert html.count('<div class="tl-row tl-row-me">') == 1
    assert html.count('<span class="tl-dot tl-dot-me">') == 1
    assert '<span class="tl-legend">' in html
    assert ">我</span>" in html

    no_me = _render(points=[dict(point, is_me=False) for point in _points()], has_me=False)
    assert '<div class="tl-row tl-row-me">' not in no_me
    assert '<span class="tl-dot tl-dot-me">' not in no_me
    assert '<span class="tl-legend">' not in no_me


def test_timeline_template_does_not_inline_script() -> None:
    """时间轴布局完全由 CSS 决定，不依赖运行时脚本（html_to_pic 截图前也不该等 JS）"""
    source = (_TEMPLATE_DIR / _TEMPLATE_NAME).read_text(encoding="utf-8")

    assert "<script" not in source.lower()
    assert "innerHTML" not in source


@pytest.mark.parametrize(
    ("offset_seconds", "expected"),
    [
        (0, 0.0),
        (3600, 10.0),
        (18000, 50.0),
        (36000, 100.0),
        (-60, 0.0),
        (72000, 100.0),
    ],
)
def test_timeline_percent_converts_offset(offset_seconds: float, expected: float) -> None:
    """距 4:00 的秒数换算成 0-100 的百分比，越界钳制到边界"""
    from nonebot_plugin_wakeuprank.image import timeline_percent

    assert timeline_percent(offset_seconds) == expected


def test_axis_ticks_match_wake_window() -> None:
    """刻度覆盖 4:00-14:00 的起床窗口，位置按百分比均分，首尾贴住轨道两端"""
    from nonebot_plugin_wakeuprank.image import get_axis_ticks

    assert get_axis_ticks() == _AXIS_TICKS


def test_timeline_uses_theme_aware_text_color() -> None:
    """文字颜色走 .text-dark：redpacket 主题里 .card 会覆盖 body 颜色，不这样会深字压深卡片"""
    html = _render()

    assert 'class="wake-timeline text-dark"' in html


@pytest.mark.asyncio
async def test_build_timeline_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """由今日记录构建时间轴点：昵称来自 larkuser，时间取 display，自己那一行被标记"""
    import nonebot_plugin_wakeuprank.image as image

    fake_user = MagicMock()
    fake_user.get_nickname.return_value = "某人"
    monkeypatch.setattr(image, "get_user", AsyncMock(return_value=fake_user))

    ranked_data: list[RankingData] = [
        {"user_id": "10086", "data": 3600, "info": None, "display": "05:00:00"},
        {"user_id": "10010", "data": 18000, "info": None, "display": "09:00:00"},
    ]

    points = await image.build_timeline_points(ranked_data, "10010")

    assert [point["user_id"] for point in points] == ["10086", "10010"]
    assert [point["time"] for point in points] == ["05:00:00", "09:00:00"]
    assert [point["percent"] for point in points] == [10.0, 50.0]
    assert [point["is_me"] for point in points] == [False, True]
    assert all(point["nickname"] == "某人" for point in points)
