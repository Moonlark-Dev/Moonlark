"""``.wakeuprank today`` 时间轴的回归测试。

背景：``today`` 原本复用 ``nonebot_plugin_ranking.generate_image`` 的排行榜卡片，把当天
早起的人按时间先后编成「第 1、2、3……名」。但 ``today`` 要表达的是「今天每个人几点起的」，
名次只是时间先后的副产品，排行榜卡片反而把注意力从时刻挪到了名次上。这一版改成垂直时间轴：
纵轴从上到下是 4:00-14:00 的起床窗口，每人一个圆点落在自己今天第一次出现的位置上，
右侧单列写「时刻 + 昵称」，起床时间贴得近的标签会在那一簇里上下摊开、用引线连回圆点。

这里钉住四件事：位置换算（含越界钳制）、标签摊开（含贴边回挪）、时间轴点由排名字段构建、
模板输出的是垂直时间轴而不是名次列表。模板渲染使用与 ``nonebot_plugin_render.render`` 相同的
Jinja 环境配置，纯模板渲染、不需要浏览器。
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
_CHART_HEIGHT = 480


def _points() -> list[dict[str, Any]]:
    return [
        {
            "user_id": "1",
            "nickname": "XiaoDeng3386",
            "time": "04:07:12",
            "percent": 1.2,
            "is_me": True,
            "label_percent": 1.2,
        },
        {
            "user_id": "2",
            "nickname": "StarWorld",
            "time": "06:31:09",
            "percent": 25.19,
            "is_me": False,
            "label_percent": 27.69,
        },
        {
            "user_id": "3",
            "nickname": "yukino",
            "time": "13:57:44",
            "percent": 99.62,
            "is_me": False,
            "label_percent": 97.12,
        },
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
        "chart_height": _CHART_HEIGHT,
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


def test_timeline_draws_one_marker_per_user() -> None:
    """每人一个圆点落在纵轴上，圆点在真实时刻、标签在摊开后的位置，两者由引线相连"""
    html = _render()

    assert html.count('<span class="tl-dot"') == 2
    assert html.count('<span class="tl-dot tl-dot-me"') == 1
    assert html.count('<span class="tl-item"') == 2
    assert html.count('<span class="tl-item tl-item-me"') == 1
    assert html.count('<line x1="0"') == 3

    # 圆点按真实时刻定位
    assert '<span class="tl-dot" style="top: 25.19%">' in html
    assert '<span class="tl-dot tl-dot-me" style="top: 1.2%">' in html
    # 标签按摊开后的位置定位（贴边的会被整体挪回图内）
    assert 'style="top: 27.69%">' in html
    assert 'style="top: 97.12%">' in html
    # 引线从圆点连到标签
    assert '<line x1="0" y1="99.62" x2="6" y2="97.12" />' in html


def test_timeline_has_no_rank_numbering() -> None:
    """不再输出「1. xxx」这种名次前缀，也不再用排行榜卡片的类名"""
    html = _render()

    for index in range(1, 4):
        assert f"{index}. " not in html
    assert "card-body ranking" not in html
    assert 'class="num"' not in html


def test_timeline_renders_vertical_axis_and_summary() -> None:
    """纵向刻度：时间标签贴在轴左侧、首尾贴边、中间居中，并画出网格线"""
    html = _render()

    for text in _AXIS_TEXTS:
        assert f">{text}</span>" in html
    assert 'class="tl-axis-label tl-axis-start" style="top: 0.0%"' in html
    assert 'class="tl-axis-label tl-axis-end" style="top: 100.0%"' in html
    assert html.count('class="tl-axis-label tl-axis-center"') == 4
    # 6 个刻度各画一条网格线
    assert html.count('<span class="tl-grid" style="top:') == 6
    assert f"height: {_CHART_HEIGHT}px" in html
    assert "今日共 3 人早起" in html
    for text in ("04:07:12", "06:31:09", "13:57:44", "XiaoDeng3386", "StarWorld", "yukino"):
        assert text in html


def test_timeline_highlights_caller() -> None:
    """调用者那一条加高亮类和橙色圆点，图例显示「我」；调用者不在列表里时不显示图例"""
    html = _render()
    assert html.count('<span class="tl-dot tl-dot-me"') == 1
    assert html.count('<span class="tl-item tl-item-me"') == 1
    assert '<span class="tl-legend">' in html
    assert ">我</span>" in html

    no_me = _render(points=[dict(point, is_me=False) for point in _points()], has_me=False)
    assert '<span class="tl-dot tl-dot-me"' not in no_me
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
    """刻度覆盖 4:00-14:00 的起床窗口，位置按百分比均分，首尾贴住轴两端"""
    from nonebot_plugin_wakeuprank.image import get_axis_ticks

    assert get_axis_ticks() == _AXIS_TICKS


def test_timeline_uses_theme_aware_text_color() -> None:
    """文字颜色走 .text-dark：redpacket 主题里 .card 会覆盖 body 颜色，不这样会深字压深卡片"""
    html = _render()

    assert 'class="wake-timeline text-dark"' in html


def test_spread_labels_centers_a_crowd() -> None:
    """同一簇里的标签以真实时刻的中心为基准等距排开，离得远的不受影响"""
    from nonebot_plugin_wakeuprank.image import spread_labels

    points = [
        {"user_id": "1", "nickname": "a", "time": "06:30:00", "percent": 50.0, "is_me": False},
        {"user_id": "2", "nickname": "b", "time": "06:31:00", "percent": 51.0, "is_me": False},
        {"user_id": "3", "nickname": "c", "time": "06:32:00", "percent": 52.0, "is_me": False},
        {"user_id": "4", "nickname": "d", "time": "10:00:00", "percent": 70.0, "is_me": False},
    ]

    laid_out = spread_labels(points, gap_percent=5.0)

    # 三个人的中心是 51，标签落在 46 / 51 / 56；远处那个人标签就在真实位置
    assert [point["label_percent"] for point in laid_out] == [46.0, 51.0, 56.0, 70.0]
    # 圆点仍然在真实时刻上
    assert [point["percent"] for point in laid_out] == [50.0, 51.0, 52.0, 70.0]


def test_spread_labels_keeps_everything_in_chart() -> None:
    """一簇标签整体挪回图内：不会跑到 4:00 之前，也不会超出 14:00"""
    from nonebot_plugin_wakeuprank.image import spread_labels

    top = spread_labels(
        [
            {"user_id": "1", "nickname": "a", "time": "04:01:00", "percent": 0.5, "is_me": False},
            {"user_id": "2", "nickname": "b", "time": "04:02:00", "percent": 1.0, "is_me": False},
            {"user_id": "3", "nickname": "c", "time": "04:03:00", "percent": 1.5, "is_me": False},
        ],
        gap_percent=5.0,
    )
    assert [point["label_percent"] for point in top] == [0.0, 5.0, 10.0]

    bottom = spread_labels(
        [
            {"user_id": "1", "nickname": "a", "time": "13:58:00", "percent": 99.0, "is_me": False},
            {"user_id": "2", "nickname": "b", "time": "13:59:00", "percent": 100.0, "is_me": False},
        ],
        gap_percent=5.0,
    )
    assert [point["label_percent"] for point in bottom] == [95.0, 100.0]


def test_spread_labels_fixes_cluster_boundary() -> None:
    """簇尾被均摊推下来后不能再压到下一个人的标签，边界处也要单调下推"""
    from nonebot_plugin_wakeuprank.image import spread_labels

    points = [
        {"user_id": str(index), "nickname": str(index), "time": "06:00:00", "percent": percent, "is_me": False}
        for index, percent in enumerate([50.0, 51.0, 52.0, 57.0])
    ]

    laid_out = spread_labels(points, gap_percent=5.0)

    # 52 那一簇的标签摊到 46/51/56，57 那个人的标签被推到 61，而不是停在 57
    assert [point["label_percent"] for point in laid_out] == [46.0, 51.0, 56.0, 61.0]


def test_label_gap_percent_matches_chart_height() -> None:
    """标签占位高度按画布高度换算成百分比，用于判定两条标签会不会叠在一起"""
    from nonebot_plugin_wakeuprank.constants import TIMELINE_CHART_HEIGHT, TIMELINE_LABEL_GAP
    from nonebot_plugin_wakeuprank.image import label_gap_percent

    assert label_gap_percent() == pytest.approx(TIMELINE_LABEL_GAP / TIMELINE_CHART_HEIGHT * 100)


@pytest.mark.asyncio
async def test_build_timeline_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """由今日记录构建时间轴点：昵称来自 larkuser，时间取 display，自己那一条被标记"""
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
    assert all("label_percent" not in point for point in points)
