from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

from nonebot_plugin_larkutils.user import get_user_id
from .utils import set_access

alc = Alconna(
    "access",
    Subcommand("ban"),
    Subcommand("pardon"),
    Subcommand("block", Args["access", str]),
    Subcommand("unblock", Args["access", str]),
    Args["subject", str],
)
access_command = on_alconna(alc, permission=SUPERUSER)


@access_command.assign("ban")
async def _(subject: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, "all", False, user_id)


@access_command.assign("pardon")
async def _(subject: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, "all", True, user_id)


@access_command.assign("block")
async def _(subject: str, access: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, access, False, user_id)


@access_command.assign("unblock")
async def _(subject: str, access: str, user_id: str = get_user_id()) -> None:
    await set_access(subject, access, True, user_id)
