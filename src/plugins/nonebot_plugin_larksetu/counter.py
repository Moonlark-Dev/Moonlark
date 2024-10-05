from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound
from nonebot.log import logger
from .models import UserData


async def add(user_id: str, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(UserData, {"user_id": user_id})
    except NoResultFound:
        logger.waring(f"{traceback.format_exc()}")
        session.add(UserData(user_id=user_id, count=1))
        await session.commit()
        return
    data.count += 1
    await session.commit()
