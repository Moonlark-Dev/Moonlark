from fastapi import Request
from nonebot import get_app

from nonebot_plugin_larkuid.session import get_user_id
from .utils.cache import access_cache


@get_app().get("/api/users/me/permissions")
async def _(_request: Request, user_id: str = get_user_id()) -> dict[str, bool]:
    # 与权限检查共用同一份内存缓存，避免两边读到不一致的权限表
    await access_cache.ensure_loaded()
    return access_cache.permissions_of(user_id)
