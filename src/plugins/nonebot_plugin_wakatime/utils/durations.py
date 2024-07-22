from nonebot.compat import type_validate_json
import httpx
from typing import Optional
from nonebot.log import logger
import traceback

from .access import get_authorization_header
from ..models import DurationsResponse


async def request_user_durations(user_name: str) -> DurationsResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://wakatime.com/api/v1/users/{user_name}/stats/last_7_days",
            headers=get_authorization_header()
        )
    logger.debug(response.text)
    return type_validate_json(DurationsResponse, response.text)


async def get_user_durations(user_name: str) -> Optional[DurationsResponse]:
    try:
        return await request_user_durations(user_name)
    except Exception:
        logger.warning(traceback.format_exc())
        return None
