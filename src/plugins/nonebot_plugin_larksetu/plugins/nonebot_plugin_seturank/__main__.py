from ... import model
from ....nonebot_plugin_larklang import LangHelper
from ....nonebot_plugin_larkuser import get_user
from ....nonebot_plugin_larkutils import get_user_id
from ... import __main__
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_htmlrender import template_to_pic
from pathlib import Path
from nonebot_plugin_alconna.uniseg import UniMessage
from sqlalchemy import select

lang = LangHelper()

@__main__.setu.assign("rank")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    result = await session.execute(select(model.UserData))
    data = result.scalars().all()
    sorted_data = sorted(data, key=lambda x: x.count, reverse=True)
    rank = 0
    await __main__.setu.finish(UniMessage().image(raw=await template_to_pic(
        Path(__file__).parent.joinpath("template").as_posix(),
        "index.html.jinja",
        {
            "title": await lang.text("rank.title", user_id),
            "footer": await lang.text("rank.footer", user_id),
            "users": [
                {
                    "rank": (rank := rank + 1),
                    "name": (await get_user(user.user_id)).nickname,
                    "count": user.count
                } for user in sorted_data
            ]
        }
    ), name="image.png"))
    