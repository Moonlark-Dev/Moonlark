from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from .model import SessionData
from .lang import lang
from ..nonebot_plugin_larkutils.user import get_user_id

account = on_alconna(Alconna(
    "account",
    Subcommand(
        "verify",
        Args["code", str]
    )
))


@account.assign("code")
async def _(session: async_scoped_session, code: str, user_id: str = get_user_id()) -> None:
    result = (await session.scalars(
        select(SessionData)
        .where(SessionData.activate_code == code)
        .where(SessionData.user_id == user_id))
    ).all()
    if len(result) != 1:
        await lang.finish("command.not_found", user_id)
    data = result[0]
    data.activate_code = None
    await session.commit()
    await lang.finish("command.verified", user_id)
