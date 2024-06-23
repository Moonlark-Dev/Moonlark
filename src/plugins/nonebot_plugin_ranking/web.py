from abc import ABC, abstractmethod
import time
from fastapi import Request
from nonebot import get_app

from ..nonebot_plugin_larkuser.utils.user import get_user
from .generator import find_user
from ..nonebot_plugin_larklang.__main__ import LangHelper
from ..nonebot_plugin_larkuid.session import get_user_id
from .lang import lang
from .types import RankingData, RankingResponse


class WebRanking(ABC):
    ID: str = ""
    NAME: str = ""
    LANG: LangHelper = lang

    def __init__(self) -> None:
        get_app().get(f"/rankings/{self.ID}")(self.handle)

    async def handle(
        self, request: Request, offset: int = 0, limit: int = 20, user_id: str = get_user_id("-1")
    ) -> RankingResponse:
        data = await self.get_sorted_data()
        index = offset
        return {
            "me": await find_user(data, user_id),
            "time": time.time(),
            "total": len(data),
            "users": [
                {
                    "user_id": user["user_id"],
                    "data": user["data"],
                    "info": user["info"],
                    "index": offset + (index := index + 1),
                    "nickname": (await get_user(user["user_id"])).nickname,
                }
                for user in data[offset : offset + limit]
            ],
        }

    @abstractmethod
    async def get_sorted_data(self) -> list[RankingData]: ...
