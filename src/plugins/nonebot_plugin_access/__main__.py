from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

from nonebot_plugin_larkutils.user import get_user_id
from .lang import lang
from .utils import set_access
from .utils.cache import access_cache

alc = Alconna(
    "access",
    Subcommand("ban", Args["subject", str]),
    Subcommand("pardon", Args["subject", str]),
    Subcommand("block", Args["access", str], Args["subject", str]),
    Subcommand("unblock", Args["access", str], Args["subject", str]),
    Subcommand("reload"),
)
# 整条 access 命令仅 SUPERUSER 可用，reload 子命令同样只允许 superuser 使用
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


@access_command.assign("reload")
async def _(user_id: str = get_user_id()) -> None:
    count = await access_cache.reload()
    await lang.finish("command.reload", user_id, count)
