from abc import ABC, abstractmethod
import time
from fastapi import Request
from nonebot import get_app

from ..nonebot_plugin_larkuser.utils.user import get_user
from .generator import find_user
from ..nonebot_plugin_larklang.__main__ import LangHelper
from ..nonebot_plugin_larkuid.session import get_user_id
from .types import RankingData, RankingResponse


class WebRanking(ABC):

    def __init__(self, id_: str, name: str, lang_: LangHelper) -> None:
        """
        初始化 WebRanking 参数
        :param id_: 排行路径
        :param name: 排行名称（键名）
        :param lang_: 插件使用的 LangHelper 对象
        """
        self.ID = id_
        self.NAME = name
        self.LANG = lang_
        get_app().get(f"/api/rankings/{self.ID}")(self.handle)

    def get_id(self) -> str:
        return self.ID

    async def get_name(self, user_id: str) -> str:
        return await self.LANG.text(self.NAME, user_id)

    async def handle(
        self, request: Request, offset: int = 0, limit: int = 20, user_id: str = get_user_id("-1")
    ) -> RankingResponse:
        data = await self.get_sorted_data()
        index = offset
        return {
            "me": await find_user(data, user_id),
            "time": time.time(),
            "title": await self.get_name(user_id),
            "total": len(data),
            "users": [
                {
                    "user_id": user["user_id"],
                    "data": user["data"],
                    "info": user["info"],
                    "index": offset + (index := index + 1),
                    "nickname": (await get_user(user["user_id"])).get_nickname(),
                }
                for user in data[offset : offset + limit]
            ],
        }

    @abstractmethod
    async def get_sorted_data(self) -> list[RankingData]: ...


rankings: list[WebRanking] = []


def register(rank: WebRanking) -> WebRanking:
    rankings.append(rank)
    return rank


@get_app().get(f"/api/rankings")
async def _(request: Request, user_id: str = get_user_id("-1")) -> dict[str, dict[str, str]]:
    response = {}
    for r in rankings:
        response[r.get_id()] = {"uri": f"/api/rankings/{r.get_id()}", "name": await r.get_name(user_id)}
    return response
