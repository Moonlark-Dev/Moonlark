from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .lang import lang

# 添加中文字体支持
font_manager.fontManager.addfont(Path("src/static/SarasaGothicSC-Regular.ttf"))
plt.rcParams["font.sans-serif"] = ["Sarasa Gothic SC"]
plt.rcParams["axes.unicode_minus"] = False

# 人品值等级颜色
LUCK_COLORS = {
    "beyond_perfect": "#FF6B6B",  # >100 红色
    "perfect": "#FFD700",  # 100 金色
    "great": "#4ECDC4",  # 85-99 青绿
    "good": "#45B7D1",  # 71-84 蓝色
    "fair": "#96CEB4",  # 57-70 浅绿
    "average": "#FFEAA7",  # 43-56 浅黄
    "below_average": "#DDA0DD",  # 29-42 梅色
    "poor": "#F0A500",  # 15-28 橙色
    "bad": "#E17055",  # 1-14 橙红
    "terrible": "#D63031",  # 0 深红
}


def _get_luck_color(value: int) -> str:
    if value > 100:
        return LUCK_COLORS["beyond_perfect"]
    if value == 100:
        return LUCK_COLORS["perfect"]
    if value >= 85:
        return LUCK_COLORS["great"]
    if value >= 71:
        return LUCK_COLORS["good"]
    if value >= 57:
        return LUCK_COLORS["fair"]
    if value >= 43:
        return LUCK_COLORS["average"]
    if value >= 29:
        return LUCK_COLORS["below_average"]
    if value >= 15:
        return LUCK_COLORS["poor"]
    if value >= 1:
        return LUCK_COLORS["bad"]
    return LUCK_COLORS["terrible"]


async def render_luck_trend_chart(
    user_id: str,
    dates: list[date],
    values: list[int],
    days: int,
    average: float,
) -> bytes:
    """生成人品走势折线图"""
    if not dates or not values:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(
            0.5,
            0.5,
            await lang.text("trend.no_data", user_id),
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=16,
        )
        ax.axis("off")
        buf = BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=200)
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()

    # 创建图表
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    # 日期转换
    date_nums = mdates.date2num([datetime.combine(d, datetime.min.time()) for d in dates])

    # 为每个数据点设置颜色
    point_colors = [_get_luck_color(v) for v in values]

    # 绘制折线
    ax.plot(
        date_nums,
        values,
        color="#6C5CE7",
        linewidth=2,
        marker="o",
        markersize=8,
        markerfacecolor=point_colors,
        markeredgecolor="#2D3436",
        markeredgewidth=1,
        zorder=3,
    )

    # 绘制平均值线
    ax.axhline(
        y=average,
        color="#E17055",
        linestyle="--",
        linewidth=1.5,
        alpha=0.8,
        label=await lang.text("trend.avg_line", user_id, round(average, 1)),
    )

    # 填充区域
    ax.fill_between(
        date_nums,
        values,
        alpha=0.15,
        color="#6C5CE7",
    )

    # 设置标题和标签
    title = await lang.text("trend.title", user_id, days)
    ax.set_title(
        title,
        fontsize=18,
        fontweight="bold",
        pad=20,
        color="#2D3436",
    )
    ax.set_xlabel(
        await lang.text("trend.xlabel", user_id),
        fontsize=13,
        color="#636E72",
    )
    ax.set_ylabel(
        await lang.text("trend.ylabel", user_id),
        fontsize=13,
        color="#636E72",
    )

    # 设置 Y 轴范围
    max_val = max(values)
    y_max = ((max_val // 10) + 1) * 10 if max_val > 100 else 100
    min_val = min(values) if values else 0
    y_min = max(0, (min_val // 10) * 10)
    ax.set_ylim(y_min, y_max)

    # 设置 X 轴格式
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days // 7)))
    plt.xticks(rotation=30, ha="right", fontsize=11)

    # 网格
    ax.grid(visible=True, alpha=0.3, linestyle="--", linewidth=0.5)
    ax.set_axisbelow(True)

    # 边框
    for spine in ax.spines.values():
        spine.set_visible(False)

    # 图例
    ax.legend(
        loc="upper right",
        fontsize=11,
        framealpha=0.9,
        facecolor="white",
        edgecolor="#DFE6E9",
    )

    # 在数据点上显示数值
    for x, y, color in zip(date_nums, values, point_colors):
        ax.annotate(
            str(y),
            (x, y),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=10,
            fontweight="bold",
            color="#2D3436",
            bbox={
                "boxstyle": "round,pad=0.2",
                "facecolor": "white",
                "alpha": 0.8,
                "edgecolor": color,
            },
        )

    # 调整布局
    plt.tight_layout()

    # 保存到 BytesIO
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=200)
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()
