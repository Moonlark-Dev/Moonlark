from nonebot_plugin_alconna import Alconna, Option, on_alconna

from .utils import get_luck_message
from ..nonebot_plugin_larkutils import get_user_id

alc = Alconna(
    "jrrp",
    Option("--rank|-r")
)
jrrp = on_alconna(alc)


@jrrp.assign("$main")
async def _(
    user_id: str = get_user_id()
) -> None:
    await jrrp.finish(
        await get_luck_message(user_id),
        at_sender=True
    )

