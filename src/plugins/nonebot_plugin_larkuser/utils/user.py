from typing import AsyncGenerator
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from ..user import *
from ..config import config
from ..models import UserData
from ..user.utils import is_user_registered


async def get_user(user_id: str, writable: bool = False) -> MoonlarkUser:
    """
    获取 Moonlark 用户

    返回的用户对象持有读取时的一份数据快照。需要修改 VimCoin、经验、好感度、血量等
    数值时，必须传入 ``writable=True`` 显式声明写意图：

    .. code-block:: python

        user = await get_user(user_id, writable=True)
        await user.add_vimcoin(10)

    写操作会持有该用户的异步写锁，并在锁内重新读取数据库中的最新值再修改，因此并发
    调用不会互相覆盖。用只读句柄调用写方法会抛出 :class:`UserNotWritable`，避免
    「读取快照 -> 修改 -> 写回」丢失其它协程的更新。

    :param user_id: 用户 ID
    :param writable: 是否允许修改该用户的数值数据
    :return: 可操作 Moonlark 用户类
    """
    if user_id == -1:
        user = MoonlarkUnknownUser(user_id, writable=writable)
    elif await is_user_registered(user_id):
        user = MoonlarkRegisteredUser(user_id, writable=writable)
    elif config.user_registered_guest:
        user = MoonlarkRegisteredGuest(user_id, writable=writable)
    else:
        user = MoonlarkGuestUser(user_id, writable=writable)
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
