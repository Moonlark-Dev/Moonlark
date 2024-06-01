from ....nonebot_plugin_larkuser.utils.user import get_user
from ... import models
from ....nonebot_plugin_larklang import LangHelper
from ....nonebot_plugin_larkutils import get_user_id
from ... import __main__
from nonebot_plugin_orm import async_scoped_session, get_scoped_session
from nonebot_plugin_alconna.uniseg import UniMessage
from ....nonebot_plugin_ranking import generate_image, WebRanking, WebUserData
from sqlalchemy import select

lang = LangHelper()


@__main__.setu.assign("rank")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    result = (await session.execute(select(models.UserData))).scalars().all()
    sorted_data = sorted(result, key=lambda x: x.count, reverse=True)
    await __main__.setu.finish(UniMessage().image(raw=await generate_image(
        [{
            "user_id": data.user_id,
            "info": None,
            "data": data.count
        } for data in sorted_data],
        user_id,
        await lang.text("rank.title", user_id)
    ), name="image.png"))


class SetuRanking(WebRanking):
    ID: str = "setu"
    NAME: str = "rank.title"
    NOTE: bool = False
    LANG: LangHelper = lang

    async def get_sorted_data(self) -> list[WebUserData]:
        session = get_scoped_session()
        result = (await session.execute(select(models.UserData))).scalars().all()
        sorted_data = sorted(result, key=lambda x: x.count, reverse=True)
        return [{
            "user_id": data.user_id,
            "info": None,
            "data": data.count,
            "nickname": (await get_user(data.user_id)).nickname
        } for data in sorted_data]


web_ranking = SetuRanking()
