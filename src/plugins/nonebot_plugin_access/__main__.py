from nonebot_plugin_alconna import Alconna, Args, At, Subcommand, on_alconna
from nonebot.permission import SUPERUSER
from .api import set_access
from ..nonebot_plugin_larkutils.user import get_user_id

alc = Alconna(
    "access",
    Subcommand("ban"),
    Subcommand("pardon"),
    Subcommand("block", Args["access", str]),
    Subcommand("unblock", Args["access", str]),
    Args["subject", str]
)
access = on_alconna(
    alc,
    permission=SUPERUSER
)


@access.assign("ban")
async def _(subject: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, "all", False, user_id)


@access.assign("pardon")
async def _(subject: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, "all", True, user_id)


@access.assign("block")
async def _(subject: str, access: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, access, False, user_id)


@access.assign("unblock")
async def _(subject: str, access: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, access, True, user_id)
