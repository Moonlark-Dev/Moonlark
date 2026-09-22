from nonebot_plugin_orm import async_scoped_session
from datetime import datetime, timedelta
from sqlalchemy import select
from nonebot_plugin_message_summary.models import GroupMessage
from .score import calculate_heat_score
from ..config import config


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


async def get_group_rankings(group_scores: dict, target_group_id: str) -> tuple[int, int, int]:
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
