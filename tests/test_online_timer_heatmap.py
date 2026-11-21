"""online-timer「在线概率热力时间轴」的回归测试。

背景：在线记录原本只保留 3 天，卡片上也只画当天那一条时段。这一版把保留期扩到一个月，
并在卡片下半部分加了一条类似 ``ghot`` 的热力时间轴，回答「某个时间点（星期几的几点）在
记录下来的数据里，这个人在线的概率是多少」。

这里钉住三件事：

- 概率口径：单元格概率 = 单元格内在线秒数 / 该单元格在统计窗口内被覆盖的秒数；
- 窗口边界与重叠记录：概率不能超过 1，30 天前那半天、今天没走完的那个小时都按实际长度做分母；
- 热力图的落点：概率对应的颜色确实画在 ``(weekday, hour)`` 那个格子上，「现在」那格有蓝色描边。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

# 2026-01-05 是周一；把它当「现在」，断言里的星期几就能直接读出来
MONDAY = datetime(2026, 1, 5, 12, 0, 0)
LAST_MONDAY = datetime(2025, 12, 29, 12, 0, 0)
MONDAY_TWO_WEEKS_AGO = datetime(2025, 12, 22, 12, 0, 0)


def _compute(intervals, now=MONDAY, window_days=14):
    from nonebot_plugin_online_timer.heatmap import compute_probability_grid

    return compute_probability_grid(iter(intervals), now, window_days)


def _monday_interval(start_hour: int, end_hour: int, day=MONDAY):
    return (
        day.replace(hour=start_hour, minute=0, second=0, microsecond=0),
        day.replace(hour=end_hour, minute=0, second=0, microsecond=0),
    )


def test_full_slot_online_gives_full_probability():
    # 窗口 14 天里周一 9-10 点只出现两次（12-29 与 01-05），两天都在线就是 100%
    grid = _compute([_monday_interval(9, 10), _monday_interval(9, 10, LAST_MONDAY)])

    assert grid.probability_at(MONDAY.replace(hour=9, minute=30)) == 1.0
    assert grid.probability_at(MONDAY.replace(hour=10, minute=30)) == 0.0


def test_partial_slot_online_gives_partial_probability():
    # 两次里只有一次在线，概率是 50%
    grid = _compute([_monday_interval(9, 10, LAST_MONDAY)])

    assert grid.probability_at(MONDAY.replace(hour=9, minute=30)) == 0.5


def test_overlapping_records_do_not_exceed_one():
    # 两天的记录各自重叠，直接相加会得到 2.0；合并区间之后两天都是 100%
    grid = _compute(
        [
            _monday_interval(9, 10),
            (
                MONDAY.replace(hour=9, minute=30),
                MONDAY.replace(hour=11, minute=0),
            ),
            _monday_interval(9, 11),
            _monday_interval(9, 10, LAST_MONDAY),
            (
                LAST_MONDAY.replace(hour=9, minute=30),
                LAST_MONDAY.replace(hour=11, minute=0),
            ),
        ]
    )

    assert grid.probability_at(MONDAY.replace(hour=9, minute=30)) == 1.0
    assert grid.probability_at(MONDAY.replace(hour=10, minute=30)) == 1.0
    assert all(probability <= 1.0 for row in grid.probabilities for probability in row)


def test_window_boundaries_are_clipped_to_covered_seconds():
    # 一整段「从窗口之前一直在线到现在」：分母同样只算窗口内的部分，所以处处是 100%
    grid = _compute([(datetime(2025, 12, 1, 0, 0), datetime(2026, 1, 6, 0, 0))])

    assert all(probability == 1.0 for row in grid.probabilities for probability in row)
    # 14 天的窗口从周一中午开始，每个 (星期, 小时) 恰好被 2 个完整小时覆盖：窗口边缘那半天
    # 若被整格计入，这里会变成 3 小时，上面「处处 100%」的断言也就跟着崩了
    assert all(covered == 3600.0 * 2 for row in grid.covered_seconds for covered in row)


def test_records_outside_window_are_ignored():
    grid = _compute([(datetime(2025, 12, 1, 9, 0), datetime(2025, 12, 2, 9, 0))])

    assert all(probability == 0.0 for row in grid.probabilities for probability in row)


def test_probability_grid_handles_empty_records():
    grid = _compute([])

    assert grid.probability_at(MONDAY) == 0.0
    assert grid.has_data(0, 0) is True


def test_heat_color_gets_darker_with_probability():
    from nonebot_plugin_online_timer.heatmap import heat_color

    # 色阶中点是写死的停靠点，顺带钉住色阶本身
    assert heat_color(0.5) == (247, 177, 102)
    assert sum(heat_color(0.0)) > sum(heat_color(0.5)) > sum(heat_color(1.0))
    # 越界的概率被钳到两端
    assert heat_color(-1.0) == heat_color(0.0)
    assert heat_color(1.5) == heat_color(1.0)


def test_draw_heatmap_paints_weekday_hour_cell():
    from PIL import Image, ImageDraw, ImageFont

    from nonebot_plugin_online_timer.heatmap import draw_heatmap, heat_color

    grid = _compute([_monday_interval(9, 10), _monday_interval(9, 10, LAST_MONDAY)])
    image = Image.new("RGB", (400, 300), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    left, top, label_width, cell_width, cell_height = 10, 60, 40, 10, 10

    draw_heatmap(
        draw,
        grid,
        MONDAY,
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        ["0:00", "12:00", "24:00"],
        "low",
        "high",
        font,
        font,
        left,
        top,
        label_width,
        cell_width,
        cell_height,
    )

    grid_left = left + label_width
    # 周一 9 点：100% 在线
    assert image.getpixel((grid_left + 9 * cell_width + 5, top + 5)) == heat_color(1.0)
    # 周一 10 点：没有在线记录
    assert image.getpixel((grid_left + 10 * cell_width + 5, top + 5)) == heat_color(0.0)
    # 「现在」（周一 12 点）那格有蓝色描边
    now_left = grid_left + 12 * cell_width
    now_color = (37, 99, 235)
    assert any(
        image.getpixel((x, y)) == now_color
        for x in range(now_left - 2, now_left + cell_width + 2)
        for y in range(top - 2, top + cell_height + 2)
    )


def test_get_last_seen_is_clamped_to_now():
    from nonebot_plugin_online_timer.__main__ import get_last_seen

    # end_time 是「最后一次发言 + 3 分钟」，会落在 now 之后
    records = [
        SimpleNamespace(end_time=MONDAY.replace(hour=8, minute=0)),
        SimpleNamespace(end_time=MONDAY.replace(hour=12, minute=3)),
    ]

    assert get_last_seen(records, MONDAY) == MONDAY
    assert get_last_seen([], MONDAY) is None


def test_retention_keeps_a_complete_probability_window():
    from nonebot_plugin_online_timer.constants import PROBABILITY_WINDOW_DAYS, RECORD_RETENTION_DAYS

    assert PROBABILITY_WINDOW_DAYS >= 30
    # 清理任务每天只跑一次，保留期必须比统计窗口多留一天，否则窗口最远端那天会被削掉
    assert RECORD_RETENTION_DAYS > PROBABILITY_WINDOW_DAYS


def _fake_records():
    """构造一批能覆盖热力图所有色阶的假记录。"""
    return [
        SimpleNamespace(
            start_time=MONDAY.replace(hour=9, minute=0),
            end_time=MONDAY.replace(hour=11, minute=0),
        ),
        SimpleNamespace(
            start_time=LAST_MONDAY.replace(hour=9, minute=0),
            end_time=LAST_MONDAY.replace(hour=10, minute=0),
        ),
        SimpleNamespace(
            start_time=MONDAY.replace(hour=8, minute=55),
            end_time=MONDAY.replace(hour=9, minute=20),
        ),
    ]


async def _render(monkeypatch, records, **kwargs) -> bytes:
    from nonebot_plugin_larkuser.utils import user as larkuser
    from nonebot_plugin_online_timer import __main__ as plugin

    async def fake_text(key: str, user_id: str, *args) -> str:
        return f"{key}:" + ",".join(str(arg) for arg in args)

    monkeypatch.setattr(plugin.lang, "text", fake_text)
    monkeypatch.setattr(larkuser, "get_user", AsyncMock(return_value=SimpleNamespace(get_nickname=lambda: "nickname")))
    return await plugin.render_online_timeline("10000", records, now=MONDAY, **kwargs)


async def test_render_only_adds_now_probability_when_viewing_others(monkeypatch):
    from io import BytesIO

    from PIL import Image

    from nonebot_plugin_online_timer import __main__ as plugin

    own = Image.open(BytesIO(await _render(monkeypatch, _fake_records())))
    other = Image.open(BytesIO(await _render(monkeypatch, _fake_records(), viewer_id="20000")))

    # 看自己时没有「现在在线的概率」那三行，卡片矮一截
    assert own.size == (plugin.CARD_WIDTH, plugin.HEAT_LABEL_Y + 26)
    assert other.size == (plugin.CARD_WIDTH, plugin.LAST_SEEN_Y + 22)
    # At 自己被当作看自己处理
    at_self = Image.open(BytesIO(await _render(monkeypatch, _fake_records(), viewer_id="10000")))
    assert at_self.size == own.size
