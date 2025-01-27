from typing import Literal
from nonebot_plugin_alconna import UniMessage
from ..utils.ranking import get_user_list
from nonebot_plugin_larkutils import get_user_id
from ..models import QuickMathUser
from ..__main__ import lang, quick_math
from nonebot_plugin_ranking import generate_image


@quick_math.assign("rank")
async def _(rank_type: Literal["total", "max"], user_id: str = get_user_id()) -> None:
    image = await generate_image(
        [
            {"user_id": user.user_id, "data": user.max_point if rank_type == "max" else user.experience, "info": None}
            async for user in get_user_list(QuickMathUser.max_point if rank_type == "max" else QuickMathUser.experience)
        ],
        user_id,
        await lang.text(f"rank.title-{1 if rank_type == 'max' else 2}", user_id),
    )
    await quick_math.finish(UniMessage().image(raw=image))
