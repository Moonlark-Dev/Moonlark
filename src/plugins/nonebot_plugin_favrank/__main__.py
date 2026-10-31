from nonebot import on_command
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import RankingData, generate_image
from sqlalchemy import select

from nonebot_plugin_larkuser.models import UserData

lang = LangHelper()
fav_rank = on_command("fav-rank")


async def get_sorted_ranking_data() -> list[RankingData]:
    """按好感度从高到低返回排行数据，供指令与 WebRanking 共用。"""
    async with get_session() as session:
        users = (
            (
                await session.execute(
                    select(UserData).where(UserData.register_time.is_not(None)).order_by(UserData.favorability.desc())
                )
            )
            .scalars()
            .all()
        )
    return [{"user_id": user.user_id, "info": None, "data": round(user.favorability * 1000)} for user in users]


@fav_rank.handle()
async def _(user_id: str = get_user_id()) -> None:
    ranked_data = await get_sorted_ranking_data()

    if not ranked_data:
        await fav_rank.finish(await lang.text("fav_rank.no_data", user_id))

    image = await generate_image(
        ranked_data,
        user_id,
        await lang.text("fav_rank.title", user_id),
    )
    await fav_rank.finish(await UniMessage().image(raw=image, name="image.png").export())
