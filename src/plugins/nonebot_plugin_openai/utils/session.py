from nonebot_plugin_orm import get_session
from typing import Optional
from ..models import GptUser


async def get_user_session(user_id: str) -> Optional[int]:
    async with get_session() as session:
        pass        # TODO        
