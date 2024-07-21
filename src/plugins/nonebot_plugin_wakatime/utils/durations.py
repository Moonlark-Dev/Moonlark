from nonebot.compat import type_validate_json
import httpx
from typing import Literal
from pydantic import BaseModel

from .access import get_authorization_header


class DurationsData(BaseModel):
    start: str
    end: str
    human_readable_total: str
    status: Literal["ok"]
    total_seconds: float
    username: str


class DurationsResponse(BaseModel):
    data: DurationsData


async def get_user_durations(user_name: str) -> DurationsResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://wakatime.com/api/v1/users/{user_name}/stats/last_7_days",
            headers=get_authorization_header()
        )
    return type_validate_json(DurationsResponse, response.text)
