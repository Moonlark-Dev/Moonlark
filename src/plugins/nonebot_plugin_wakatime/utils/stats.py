import traceback
from typing import Optional
from nonebot import logger
import httpx
from nonebot.compat import type_validate_json
from .token import get_token
from ..__main__ import lang
from ..models import StatsResponse, StatsProject

DURATIONS_URL = "https://wakatime.com/api/v1/users/current/stats/last_7_days"


async def get_current_user_stats(access_token: str) -> StatsResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(DURATIONS_URL, headers={"Authorization": f"Bearer {access_token}"})
        data = response.text
        logger.debug(data)
    return type_validate_json(StatsResponse, data)


async def get_stats_by_user(user_id: str) -> Optional[StatsResponse]:
    access_token = await get_token(user_id)
    if access_token is not None:
        try:
            return await get_current_user_stats(access_token)
        except Exception:
            logger.warning(f"获取 WakaTime 信息失败: {traceback.format_exc()}")


async def get_user_stats(user_id: str) -> Optional[StatsResponse]:
    d = await get_stats_by_user(user_id)
    if d is not None and not d.data.projects:
        d.data.projects = [StatsProject(
            name=await lang.finish("main.none", user_id),
            text=await lang.finish("main.zero", user_id),
        )]
    return d
