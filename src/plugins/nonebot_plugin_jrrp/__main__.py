from nonebot_plugin_alconna import Alconna, Option, on_alconna
from nonebot_plugin_chat.matcher.group import post_group_event
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.jrrp import get_luck_value
from nonebot_plugin_schedule.utils import complete_schedule
from .utils import get_luck_message
from nonebot_plugin_larkutils import get_user_id
from nonebot.adapters import Bot, Event
from .lang import lang

alc = Alconna("jrrp", Option("--rank|-r|r"), Option("--rank-r|-rr|rr"))
jrrp = on_alconna(alc)


@jrrp.assign("$main")
async def _(bot: Bot, event: Event, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    await complete_schedule(user_id, "jrrp")
    await post_group_event(
        group_id,
        await lang.text("chat_event", user_id, await get_nickname(user_id, bot, event), await get_luck_value(user_id)),
        "probability"
    )
    await jrrp.finish(await get_luck_message(user_id), at_sender=True)
