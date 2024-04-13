from .model import GroupData
from nonebot_plugin_orm import async_scoped_session
from datetime import datetime, timedelta
from sqlalchemy.exc import NoResultFound

async def is_group_cooled(group_id: str, session: async_scoped_session) -> tuple[bool, float]:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        return True, 0
    remain = (timedelta(minutes=data.cool_down_time) - (datetime.now() - data.last_use)).total_seconds()
    return remain <= 0, remain


async def on_group_use(group_id: str, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        session.add(GroupData(
            group_id=group_id,
            last_use=datetime.now()
        ))
    else:
        data.last_use = datetime.now()
    await session.commit()
