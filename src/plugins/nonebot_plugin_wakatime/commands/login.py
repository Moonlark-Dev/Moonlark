from nonebot import logger
from nonebot_plugin_orm import get_session

from nonebot_plugin_larkutils import get_user_id
from ..__main__ import matcher, lang
from ..utils import login, token, get_user_stats
from ..models import User


@matcher.assign("login")
async def _(user_id: str = get_user_id()) -> None:
    await login.request_login(user_id)
    code = await login.wait_user_code()
    login.clean()
    if code is None:
        await lang.finish("login.abort", user_id)
    await token.update_token(user_id, await token.request_token(code))
    d = await get_user_stats(user_id)
    if d is None:
        await lang.finish("login.failed", user_id)
    logger.info(f"用户 {user_id} 已登录到 WakaTime {d.data.username}")
    await lang.finish("login.ok", user_id, d.data.username)
