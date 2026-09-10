from typing import Literal

from nonebot_plugin_alconna import Arparma, UniMessage
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_ranking import generate_image

from ..__main__ import lang, quick_math
from ..models import QuickMathUser
from ..utils.ranking import get_user_list


@quick_math.assign("rank")
async def handle(result: Arparma, user_id: str = get_user_id()) -> None:
    """查看积分排行：默认历史最高分排行，``-t/--total`` 切换为总分排行。"""
    rank_type: Literal["max", "total"] = "total" if result.query("rank.total") is not None else "max"
    order_by = QuickMathUser.experience if rank_type == "total" else QuickMathUser.max_point
    data = [
        {"user_id": user.user_id, "data": user.max_point if rank_type == "max" else user.experience, "info": None}
        async for user in get_user_list(order_by)
    ]
    title = await lang.text(f"rank.title-{1 if rank_type == 'max' else 2}", user_id)
    image = await generate_image(data, user_id, title)
    await quick_math.finish(UniMessage().image(raw=image, name="image.png"))
