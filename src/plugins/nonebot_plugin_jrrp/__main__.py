from nonebot_plugin_alconna import Alconna, Option, on_alconna, Args
from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_schedule.utils import complete_schedule
from datetime import date, timedelta
from .utils import get_luck_message, lang
from nonebot_plugin_larkutils import get_user_id

alc = Alconna("jrrp", Option("--rank|-r"), Option("--get|-g", Args["value", int]))
jrrp = on_alconna(alc)


@jrrp.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    await complete_schedule(user_id, "jrrp")
    await jrrp.finish(await get_luck_message(user_id), at_sender=True)


@jrrp.assign("get")
async def _(value: int, user_id: str = get_user_id()) -> None:
    d = date.today()
    for _ in range(365):
        d += timedelta(1)
        if get_luck_value(user_id, d) == value:
            await lang.finish("get.found", user_id, value, d.isoformat())
    await lang.finish("get.not_found", user_id)

        
