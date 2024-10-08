from nonebot_plugin_orm import get_session
from sqlalchemy.exc import NoResultFound

from ..nonebot_plugin_larkuser.models import UserData
from nonebot.log import logger


async def is_user_registered(user_id: str):
    async with get_session() as session:
        try:
            data = await session.get_one(UserData, {"user_id": user_id})
            return data.register_time is not None
        except NoResultFound:
            logger.waring(f"{traceback.format_exc()}")
            return False
