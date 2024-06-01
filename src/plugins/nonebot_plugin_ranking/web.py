from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html

from ..nonebot_plugin_larklang.__main__ import LangHelper
from ..nonebot_plugin_larkuid.session import get_user_id
from .lang import lang
from .typing import WebUserData


class WebRanking(ABC):
    ID: str = ""
    NOTE: bool = False
    NAME: str = ""
    LANG: LangHelper = lang

    def __init__(self) -> None:
        get_app().get(f"/ranking/{self.ID}")(self.handle)

    async def handle(self, request: Request, user_id: Optional[str] = get_user_id()):
        user_id = user_id or "-1"
        data = await self.get_sorted_data()
        return PlainTextResponse(
            await template_to_html(
                Path(__file__).parent.joinpath("template").as_posix(),
                "web.html.jinja",
                user_id=user_id,
                index=await lang.text("web.index", user_id, len(data)),
                ranking=await lang.text("web.ranking", user_id),
                nickname=await lang.text("web.nickname", user_id),
                uid=await lang.text("web.uid", user_id),
                note=await lang.text("web.note", user_id),
                data=await lang.text("web.data", user_id),
                title=await self.LANG.text(self.NAME, user_id),
                has_note=self.NOTE,
                users=data,
            ),
            media_type="text/html",
        )

    @abstractmethod
    async def get_sorted_data(self) -> list[WebUserData]: ...
