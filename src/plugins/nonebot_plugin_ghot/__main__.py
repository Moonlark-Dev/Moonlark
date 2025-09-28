from datetime import datetime, timedelta
from typing import List, Tuple
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties
import numpy as np

from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, UniMessage

from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot_plugin_message_summary.models import GroupMessage

from .config import config


# Initialize language helper
lang = LangHelper()

# Create command matcher for /ghot
ghot_cmd = on_alconna(
    Alconna(
        "ghot",
        Subcommand("history"),
    )
)


async def calculate_heat_score(
    messages_timestamps: List[datetime], current_time: datetime, delta_t: int, r_max: float = 10.0
) -> int:
    """
    Calculate group heat score based on message timestamps using linear weight decay algorithm.

    Args:
        messages_timestamps: List of message timestamps
        current_time: Current time for calculation
        delta_t: Time window in seconds
        r_max: Maximum message rate (messages/second)

    Returns:
        Heat score (0-10000)
    """
    # Filter messages within the time window
    valid_messages = [t for t in messages_timestamps if delta_t >= (current_time - t).total_seconds() >= 0]

    # Calculate total weight W
    total_weight = 0.0
    for t_i in valid_messages:
        age = (current_time - t_i).total_seconds()
        weight_i = 1.0 - age / delta_t
        total_weight += weight_i

    # Calculate maximum weight W_max
    max_weight = r_max * delta_t

    # Calculate heat score S
    if max_weight == 0:
        score = 0
    else:
        score = round((total_weight / max_weight) * 10000)
        score = min(score, 10000)  # Ensure score doesn't exceed 10000

    return score


async def get_group_hot_score(group_id: str, session: async_scoped_session) -> Tuple[int, int, int]:
    """
    Get group heat scores for 1, 5, and 15 minute windows.

    Args:
        group_id: Group ID
        session: Database session

    Returns:
        Tuple of (1min_score, 5min_score, 15min_score)
    """
    # Get current time
    current_time = datetime.now()

    # Calculate time windows
    time_windows = [60, 300, 900]  # 1, 5, 15 minutes in seconds

    # Get messages for this group within the last 15 minutes (longest window)
    start_time = current_time - timedelta(seconds=900)
    result = await session.scalars(
        select(GroupMessage).where(GroupMessage.group_id == group_id).where(GroupMessage.timestamp >= start_time)
    )
    messages = result.all()

    # Extract timestamps
    timestamps = [msg.timestamp for msg in messages]

    # Calculate scores for each time window
    scores = []
    for delta_t in time_windows:
        score = await calculate_heat_score(timestamps, current_time, delta_t, config.ghot_max_message_rate)
        scores.append(score)

    return tuple(scores)


async def get_all_groups_scores(session: async_scoped_session) -> dict:
    """
    Get heat scores for all groups.

    Args:
        session: Database session

    Returns:
        Dictionary mapping group_id to (1min_score, 5min_score, 15min_score)
    """
    # Get current time
    current_time = datetime.now()

    # Calculate time windows
    time_windows = [60, 300, 900]  # 1, 5, 15 minutes in seconds

    # Get all unique group IDs
    result = await session.scalars(select(GroupMessage.group_id).distinct())
    group_ids = result.all()

    # Get all messages within the last 15 minutes
    start_time = current_time - timedelta(seconds=900)
    result = await session.scalars(select(GroupMessage).where(GroupMessage.timestamp >= start_time))
    all_messages = result.all()

    # Group messages by group_id
    messages_by_group = {}
    for msg in all_messages:
        if msg.group_id not in messages_by_group:
            messages_by_group[msg.group_id] = []
        messages_by_group[msg.group_id].append(msg.timestamp)

    # Calculate scores for each group
    group_scores = {}
    for group_id in group_ids:
        timestamps = messages_by_group.get(group_id, [])
        scores = []
        for delta_t in time_windows:
            score = await calculate_heat_score(timestamps, current_time, delta_t, config.ghot_max_message_rate)
            scores.append(score)
        group_scores[group_id] = tuple(scores)

    return group_scores


async def get_group_rankings(group_scores: dict, target_group_id: str) -> Tuple[int, int, int]:
    """
    Get rankings for a specific group.

    Args:
        group_scores: Dictionary mapping group_id to (1min_score, 5min_score, 15min_score)
        target_group_id: Target group ID

    Returns:
        Tuple of (1min_rank, 5min_rank, 15min_rank)
    """
    if target_group_id not in group_scores:
        return 0, 0, 0

    target_scores = group_scores[target_group_id]

    # Get all scores for each time window
    scores_1min = sorted([scores[0] for scores in group_scores.values()], reverse=True)
    scores_5min = sorted([scores[1] for scores in group_scores.values()], reverse=True)
    scores_15min = sorted([scores[2] for scores in group_scores.values()], reverse=True)

    # Find rankings (using proper ranking that handles duplicates)
    rank_1min = scores_1min.index(target_scores[0]) + 1
    rank_5min = scores_5min.index(target_scores[1]) + 1
    rank_15min = scores_15min.index(target_scores[2]) + 1

    return rank_1min, rank_5min, rank_15min


@ghot_cmd.assign("$main")
async def handle_ghot_command(
    _event: GroupMessageEvent,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """
    Handle /ghot command to show group heat scores and rankings.
    """
    # Get scores for current group
    scores = await get_group_hot_score(group_id, session)

    # Get scores for all groups
    all_scores = await get_all_groups_scores(session)

    # Get rankings for current group
    rankings = await get_group_rankings(all_scores, group_id)

    # Format response
    response = await lang.text(
        "ghot.response",
        user_id,
        scores[0],
        scores[1],
        scores[2],  # 1min, 5min, 15min scores
        rankings[0],
        rankings[1],
        rankings[2],  # 1min, 5min, 15min rankings
    )

    await ghot_cmd.finish(response)


@ghot_cmd.assign("history")
async def handle_ghot_history_command(
    _event: GroupMessageEvent,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """
    Handle /ghot history command to show group heat score history chart.
    """
    # Get all messages for this group
    result = await session.scalars(select(GroupMessage).where(GroupMessage.group_id == group_id))
    messages = result.all()

    if not messages:
        response = await lang.text("ghot.no_messages", user_id)
        await ghot_cmd.finish(response)

    # Get the earliest and latest timestamps
    timestamps = [msg.timestamp for msg in messages]
    earliest_time = min(timestamps)
    latest_time = max(timestamps)

    # Create 10-minute intervals
    interval = timedelta(minutes=10)
    current_time = earliest_time + interval / 2
    time_points = []
    heat_scores = []

    # Calculate heat score for each 10-minute interval
    while current_time <= latest_time:
        # For history, we'll use a 15-minute window (same as the main command)
        window_end = current_time + interval / 2
        window_start = current_time - interval / 2

        # Filter messages within the window
        window_messages = [t for t in timestamps if window_start <= t <= window_end]

        # Calculate heat score using the same algorithm as the main function
        score = await calculate_heat_score(
            window_messages, current_time, round(interval.total_seconds()), config.ghot_max_message_rate
        )
        heat_scores.append(score)
        time_points.append(current_time + interval / 2)

        current_time += interval

    # Create the chart
    plt.figure(figsize=(12, 6))
    plt.plot(time_points, heat_scores, marker="o", linestyle="-", linewidth=2, markersize=4)
    plt.title(await lang.text("history.title", user_id))
    plt.xlabel(await lang.text("history.xlabel", user_id))
    plt.ylabel(await lang.text("history.ylabel", user_id))
    plt.grid(True, alpha=0.3)

    # Format x-axis as time
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=60))
    plt.xticks(rotation=45)

    # Set y-axis limits
    plt.ylim(0, round(max(heat_scores) // 10 * 10 + 10))

    # Adjust layout to prevent label cutoff
    plt.tight_layout()

    # Save to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=300, bbox_inches="tight")
    buf.seek(0)
    plt.close()

    # Send the chart
    await ghot_cmd.finish(UniMessage().image(raw=buf.getvalue()))
