from nonebot_plugin_alconna import UniMessage

from ...nonebot_plugin_render.render import render_template
from ..utils.item import get_bag_items
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import bag
from ..__main__ import lang
from ..config import config

STAR_COLORS = {1: "secondary", 2: "success", 3: "info", 4: "purple", 5: "warning"}


@bag.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    item_list = await get_bag_items(user_id)
    size_percent = f"{len(item_list) / config.bag_max_size:.2%}"
    await bag.finish(
        UniMessage().image(
            raw=await render_template(
                "bag.html.jinja",
                await lang.text("list.title", user_id),
                user_id,
                {
                    "size": await lang.text("list.size", user_id, len(item_list), config.bag_max_size, size_percent),
                    "size_percent": size_percent,
                    "items": [
                        {
                            "name": await item.stack.getName(),
                            "count": await lang.text("list.count", user_id, item.stack.count),
                            "index": await lang.text("list.index", user_id, item.index),
                            "text_color": STAR_COLORS[item.stack.item.getProperties()["star"]],
                        }
                        for item in item_list
                    ],
                },
            )
        )
    )
