from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from .web.sub_account import get_bind_cache
from nonebot_plugin_larkutils import get_user_id, set_main_account
from .lang import lang
from .models import SessionData

account = on_alconna(Alconna("account", Subcommand("verify", Args["code", str]), Subcommand("bind", Args["key", str])))


@account.assign("code")
async def _(session: async_scoped_session, code: str, user_id: str = get_user_id()) -> None:
    result = (
        await session.scalars(
            select(SessionData).where(SessionData.activate_code == code).where(SessionData.user_id == user_id)
        )
    ).all()
    if len(result) != 1:
        await lang.finish("command.not_found", user_id)
    data = result[0]
    data.activate_code = None
    await session.commit()
    await lang.finish("command.verified", user_id)


@account.assign("key")
async def _(key: str, user_id: str = get_user_id()) -> None:
    try:
        data = get_bind_cache(user_id)
    except KeyError:
        await lang.finish("sa.key_error", user_id)
        return
    if key != data["activate_code"]:
        await lang.finish("sa.wrong_key", user_id)
    await set_main_account(data["account"], user_id)
    await lang.finish("sa.done", user_id, data["account"])
