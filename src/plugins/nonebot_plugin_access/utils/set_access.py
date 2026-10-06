from typing import Optional

from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..lang import lang
from ..models import SubjectData
from .cache import access_cache


async def set_access(subject: str, access: str, available: bool, user_id: Optional[str] = None) -> None:
    async with get_session() as session:
        data = await session.scalar(
            select(SubjectData).where(SubjectData.subject == subject).where(SubjectData.name == access)
        )
        if data is not None:
            data.available = available
        else:
            session.add(SubjectData(subject=subject, name=access, available=available))
        await session.commit()
    # 权限表已更新，立即重新拉取一次，权限检查不必等到下一次定时刷新
    await access_cache.reload()
    if user_id is not None:
        await lang.finish("command.set", user_id, subject, access, available)
