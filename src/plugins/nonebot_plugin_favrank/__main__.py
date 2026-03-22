from nonebot import on_command
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import generate_image
from sqlalchemy import select

from nonebot_plugin_larkuser.models import UserData

lang = LangHelper()
fav_rank = on_command("fav-rank")


@fav_rank.handle()
async def _(user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        ranked_data = (
            (
                await session.execute(
                    select(UserData)
                    .where(UserData.register_time.is_not(None))
                    .order_by(UserData.favorability.desc())
                )
            )
            .scalars()
            .all()
        )

    if not ranked_data:
        await fav_rank.finish(await lang.text("fav_rank.no_data", user_id))

    image = await generate_image(
        [{"user_id": data.user_id, "info": None, "data": data.favorability} for data in ranked_data],
        user_id,
        await lang.text("fav_rank.title", user_id),
    )
    await fav_rank.finish(UniMessage().image(raw=image, name="image.png"))
