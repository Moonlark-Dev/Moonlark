from ... import model
from ....nonebot_plugin_larklang import LangHelper
from ....nonebot_plugin_larkutils import get_user_id
from ... import __main__
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna.uniseg import UniMessage
from ....nonebot_plugin_ranking import generate_image
from sqlalchemy import select

lang = LangHelper()


@__main__.setu.assign("rank")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    result = (await session.execute(select(model.UserData))).scalars().all()
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
