from typing import AsyncGenerator
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from ..user import *
from ..config import config
from ..models import UserData
from ..user.utils import is_user_registered


async def get_user(user_id: str) -> MoonlarkUser:
    """
    获取 Moonlark 用户
    :param user_id: 用户 ID
    :return: 可操作 Moonlark 用户类
    """
    if user_id == -1:
        user = MoonlarkUnknownUser(user_id)
    elif await is_user_registered(user_id):
        user = MoonlarkRegisteredUser(user_id)
    elif config.user_registered_guest:
        user = MoonlarkRegisteredGuest(user_id)
    else:
        user = MoonlarkGuestUser(user_id)
    await user.setup_user()
    return user

async def get_registered_user_ids() -> list[str]:
    async with get_session() as session:
        return list(await session.scalars(select(UserData.user_id).where(UserData.register_time != None)))

async def get_registered_users() -> AsyncGenerator[MoonlarkRegisteredUser, None]:
        for user_id in await get_registered_user_ids():
            user = await get_user(user_id)
            if isinstance(user, MoonlarkRegisteredUser):
                yield user

async def get_registered_user_list() -> list[MoonlarkRegisteredUser]:
    return [u async for u in get_registered_users()]
