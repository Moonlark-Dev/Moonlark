from typing import Any
from nonebot_plugin_session import SessionId, SessionIdType
from nonebot.params import Depends

async def _get_group_id(
    group_id: str = SessionId(
        SessionIdType.GROUP,
        include_bot_type=False,
        include_bot_id=False
    )
) -> str:
    return group_id

def get_group_id() -> Any:
    return Depends(_get_group_id)