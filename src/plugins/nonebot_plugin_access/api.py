from typing import Optional

from nonebot_plugin_orm import get_scoped_session
from sqlalchemy import select

from .lang import lang
from .models import SubjectData


async def set_access(subject: str, access: str, available: bool, user_id: Optional[str] = None) -> None:
    session = get_scoped_session()
    data = await session.scalar(
        select(SubjectData).where(SubjectData.subject == subject).where(SubjectData.name == access)
    )
    if data is not None:
        data.available = available
    else:
        session.add(SubjectData(subject=subject, name=access, available=available))
    await session.commit()
    if user_id is not None:
        await lang.finish("command.set", user_id, subject, access, available)
