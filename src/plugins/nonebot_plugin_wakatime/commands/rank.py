from nonebot_plugin_alconna import UniMessage

from ...nonebot_plugin_ranking import generate_image
from ..utils import get_sorted_ranking_data
from ..__main__ import lang, matcher
from ...nonebot_plugin_larkutils import get_user_id


@matcher.assign("rank")
async def _(user_id: str = get_user_id()) -> None:
    await matcher.finish(UniMessage.image(raw=await generate_image(
        await get_sorted_ranking_data(),
        user_id,
        await lang.text("ranking.title", user_id)
    )))
