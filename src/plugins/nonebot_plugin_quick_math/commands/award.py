from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic

from ..utils.award import get_cycle_data, get_remain, get_user_level, get_rank, get_user_point, get_award_pawcoin
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang, quick_math


@quick_math.assign("award")
async def _(user_id: str = get_user_id()) -> None:
    data = await get_cycle_data()
    remain_hours, remain_mins = await get_remain()
    point = await get_user_point(user_id)
    await quick_math.finish(
        UniMessage().image(
            raw=await md_to_pic(
                await lang.text(
                    "award.info",
                    user_id,
                    remain_hours,
                    remain_mins,
                    data["number"],
                    point,
                    rank := await get_rank(point),
                    level := await get_user_level(rank),
                    await get_award_pawcoin(point, level),
                )
            )
        )
    )
