from ..user import *
from ..config import config
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
