from datetime import datetime, timedelta
from sqlalchemy import select
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_message_summary.models import GroupMessage
from ..config import config


async def calculate_heat_score(
    messages_timestamps: list[datetime], current_time: datetime, delta_t: int, r_max: float = 10.0
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


async def get_group_hot_score(group_id: str, session: async_scoped_session) -> tuple[int, int, int]:
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
