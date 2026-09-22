from typing import Tuple
from nonebot_plugin_orm import get_scoped_session

from .utils.score import get_group_hot_score as _get_group_hot_score


async def get_group_hot_score(group_id: str) -> Tuple[int, int, int]:
    """
    Get group heat scores for 1, 5, and 15 minute windows.

    Args:
        group_id: Group ID

    Returns:
        Tuple of (1min_score, 5min_score, 15min_score)
    """
    session = get_scoped_session()
    s = await _get_group_hot_score(group_id, session)
    await session.close()
    return s
