"""``.wakeuprank today`` 的时间轴渲染。

今日排行原本复用 ``nonebot_plugin_ranking.generate_image`` 的排行榜卡片（第 1、2、3……
名依次排下来）。但 `today` 展示的是「今天每个人几点起的」，名次只是时间先后的副产品，
用排行榜卡片会把关注点从「他几点起的」挪到「他第几名」。这里改为垂直时间轴：纵轴从上
到下是 4:00-14:00 的起床窗口，每人一个圆点落在自己今天第一次出现的时刻上，右侧单列
标签写「时刻 + 昵称」。起床时间贴得很近的几个人，标签会在那一簇里上下摊开、用引线连回
自己的圆点，不会叠在一起。
"""

import operator
from typing import NotRequired, TypedDict

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_ranking import RankingData
from nonebot_plugin_render.render import render_template

from .constants import TIMELINE_AXIS_HOURS, TIMELINE_CHART_HEIGHT, TIMELINE_LABEL_GAP, TIMELINE_SPAN_SECONDS
from .lang import lang


class TimelinePoint(TypedDict):
    """时间轴上的一个点"""

    user_id: str
    nickname: str
    time: str
    percent: float
    is_me: bool
    # 标签的纵向位置：大多数时候等于 percent，同一簇里的人会被上下摊开
    label_percent: NotRequired[float]


class AxisTick(TypedDict):
    """时间轴上的一个刻度

    ``align`` 决定标签相对刻度线怎么对齐：首尾两个刻度贴住轴的两端（``start`` / ``end``），
    中间的居中对齐。都按 ``percent`` 定位，所以标签与横线严格对齐。
    """

    text: str
    percent: float
    align: str


def timeline_percent(offset_seconds: float) -> float:
    """把「距 4:00 的秒数」换算成时间轴上的百分比位置（限制在 0-100 之间）"""
    if TIMELINE_SPAN_SECONDS <= 0:
        return 0.0
    percent = offset_seconds / TIMELINE_SPAN_SECONDS * 100
    return round(min(100.0, max(0.0, percent)), 2)


async def build_timeline_points(ranked_data: list[RankingData], user_id: str) -> list[TimelinePoint]:
    """把今日起床记录转成时间轴上的点

    Args:
        ranked_data: 今日记录，``data`` 是距 4:00 的秒数、``display`` 是 HH:MM:SS 文本
        user_id: 调用者，用于高亮自己那一条

    Returns:
        按 ``ranked_data`` 顺序（即起床时间先后）排列的时间轴点（还没排标签位置）
    """
    points: list[TimelinePoint] = []
    for item in ranked_data:
        record_user_id = item["user_id"]
        nickname = (await get_user(record_user_id)).get_nickname()
        points.append(
            {
                "user_id": record_user_id,
                "nickname": nickname,
                "time": item.get("display") or "",
                "percent": timeline_percent(float(item["data"])),
                "is_me": record_user_id == user_id,
            },
        )
    return points


def label_gap_percent() -> float:
    """一条标签占掉的纵向高度换算成百分比，用于判定两条标签会不会叠在一起"""
    if TIMELINE_CHART_HEIGHT <= 0:
        return 0.0
    return TIMELINE_LABEL_GAP / TIMELINE_CHART_HEIGHT * 100


def spread_labels(points: list[TimelinePoint], gap_percent: float | None = None) -> list[TimelinePoint]:
    """给每个点算出标签的纵向位置，同一簇里贴太近的标签上下摊开

    标签高度固定，所以把「相邻两个人的起床时间挨得比一条标签还近」的人连成一簇，
    在簇内以这些人的真实时刻的中心为基准等距排开，再整体挪回 0-100% 区间。
    这样簇里的人距真实时刻的偏移最小（上下各一半），圆点仍然落在真实时刻上。
    """
    if gap_percent is None:
        gap_percent = label_gap_percent()
    laid_out: list[TimelinePoint] = []
    cluster: list[TimelinePoint] = []

    def flush() -> None:
        if not cluster:
            return
        count = len(cluster)
        center = sum(point["percent"] for point in cluster) / count
        start = center - (count - 1) * gap_percent / 2
        # 整簇挪回图内：优先不让第一条标签跑到 4:00 之前，再不让最后一条超出 14:00
        start = max(0.0, min(start, 100.0 - (count - 1) * gap_percent))
        for index, point in enumerate(cluster):
            laid_out.append(dict(point, label_percent=round(start + index * gap_percent, 2)))  # type: ignore[typeddict-item]
        cluster.clear()

    for point in sorted(points, key=operator.itemgetter("percent")):
        if cluster and point["percent"] - cluster[-1]["percent"] >= gap_percent:
            flush()
        cluster.append(point)
    flush()

    # 簇边界处可能还差一点点（均摊把尾巴推到了下一个人的位置上）：单调下推补齐，
    # 再把整列挪回图内，极端拥挤时允许顶部轻微溢出，但不允许标签互相盖住。
    for index in range(1, len(laid_out)):
        laid_out[index]["label_percent"] = max(
            laid_out[index]["label_percent"],
            round(laid_out[index - 1]["label_percent"] + gap_percent, 2),
        )
    if laid_out and laid_out[-1]["label_percent"] > 100:
        overflow = laid_out[-1]["label_percent"] - 100
        for point in laid_out:
            point["label_percent"] = max(0.0, round(point["label_percent"] - overflow, 2))
    return laid_out


def get_axis_ticks() -> list[AxisTick]:
    """时间轴刻度及各自的百分比位置，如 ``04:00`` 位于 0%、``14:00`` 位于 100%"""
    labels = [f"{hour:02d}:00" for hour in TIMELINE_AXIS_HOURS]
    last = len(labels) - 1
    ticks: list[AxisTick] = []
    for index, label in enumerate(labels):
        if index == 0:
            align = "start"
        elif index == last:
            align = "end"
        else:
            align = "center"
        ticks.append({"text": label, "percent": round(index / last * 100, 2) if last else 0.0, "align": align})
    return ticks


async def generate_timeline_image(points: list[TimelinePoint], user_id: str, title: str) -> bytes:
    """把时间轴渲染成图片"""
    has_me = any(point["is_me"] for point in points)
    return await render_template(
        "wakeuprank_timeline.html.jinja",
        title,
        user_id,
        {
            "points": spread_labels(points),
            # 刻度、圆点、标签都用同一套百分比定位，标签和横线才不会错位
            "axis_ticks": get_axis_ticks(),
            "chart_height": TIMELINE_CHART_HEIGHT,
            "has_me": has_me,
            "count_label": await lang.text("wakeuprank.timeline.count", user_id, len(points)),
            "me_label": await lang.text("wakeuprank.timeline.me", user_id) if has_me else "",
        },
    )
