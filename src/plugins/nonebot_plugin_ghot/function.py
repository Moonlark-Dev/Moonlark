from typing import Tuple
from nonebot_plugin_orm import get_scoped_session

from .utils.group import resolve_group_keys
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
    try:
        # 合并同一物理群在 QQ 官方与 OneBot 下的两个群键
        group_keys = await resolve_group_keys(session, group_id)
        return await _get_group_hot_score(group_keys, session)
    finally:
        await session.close()
