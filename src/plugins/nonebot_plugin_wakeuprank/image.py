"""``.wakeuprank today`` 的时间轴渲染。

今日排行原本复用 ``nonebot_plugin_ranking.generate_image`` 的排行榜卡片（第 1、2、3……
名依次排下来）。但 `today` 展示的是「今天每个人几点起的」，名次只是时间先后的副产品，
用排行榜卡片会把关注点从「他几点起的」挪到「他第几名」。这里改为时间轴：
横轴是 4:00-14:00 的起床窗口，每人一行，圆点落在自己今天第一次出现的位置上。
"""

from typing import TypedDict

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_ranking import RankingData
from nonebot_plugin_render.render import render_template

from .constants import TIMELINE_AXIS_HOURS, TIMELINE_SPAN_SECONDS
from .lang import lang


class TimelinePoint(TypedDict):
    """时间轴上的一个点"""

    user_id: str
    nickname: str
    time: str
    percent: float
    is_me: bool


class AxisTick(TypedDict):
    """时间轴上的一个刻度

    ``align`` 决定标签相对刻度线怎么对齐：首尾两个刻度贴住轨道两端（``start`` / ``end``），
    中间的居中对齐。都按 ``percent`` 定位，所以标签与竖线严格对齐。
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
        user_id: 调用者，用于高亮自己那一行

    Returns:
        按 ``ranked_data`` 顺序（即起床时间先后）排列的时间轴点
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
            "points": points,
            # 刻度与圆点用同一套百分比定位，标签和竖线才不会错位
            "axis_ticks": get_axis_ticks(),
            "has_me": has_me,
            "count_label": await lang.text("wakeuprank.timeline.count", user_id, len(points)),
            "me_label": await lang.text("wakeuprank.timeline.me", user_id) if has_me else "",
        },
    )
