from nonebot_plugin_alconna import UniMessage
from datetime import datetime

from ...utils.overflow import get_overflow_items

from ....nonebot_plugin_render.render import render_template
from ...utils.item import get_bag_items
from ....nonebot_plugin_larkutils.user import get_user_id
from ...__main__ import bag
from ...__main__ import lang
from ...config import config
from ..bag import STAR_COLORS


@bag.assign("overflow")
async def _(user_id: str = get_user_id()) -> None:
    await bag.finish(
        UniMessage().image(
            raw=await render_template(
                "bag_overflow.html.jinja",
                await lang.text("overflow.title", user_id),
                user_id,
                {
                    "items": [
                        {
                            "name": item_data["item"].getName(),
                            "count": await lang.text("list.count", user_id, item_data["item"].count),
                            "index": await lang.text("list.index", user_id, item_data["index"]),
                            "text_color": STAR_COLORS[item_data["item"].item.getProperties()["star"]],
                        }
                        async for item_data in get_overflow_items()
                        if (datetime.now() - item_data["time"]).total_seconds() > config.overflow_protect_hours * 3600
                    ],
                    "my_items": [
                        {
                            "name": item_data["item"].getName(),
                            "count": await lang.text("list.count", user_id, item_data["item"].count),
                            "index": await lang.text("list.index", user_id, item_data["index"]),
                            "text_color": STAR_COLORS[item_data["item"].item.getProperties()["star"]],
                        }
                        async for item_data in get_overflow_items()
                        if (datetime.now() - item_data["time"]).total_seconds() < config.overflow_protect_hours * 3600
                        and item_data["item"].user_id == user_id
                    ],
                    "title_protect": await lang.text("overflow_list.title", user_id),
                    "title_getable": await lang.text("overflow_list.title_getable", user_id),
                },
            )
        )
    )
