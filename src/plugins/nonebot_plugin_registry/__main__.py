import asyncio
from datetime import datetime

from nonebot import on_command
from nonebot.params import ArgPlainText
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session, get_scoped_session
from sqlalchemy import select

from ..nonebot_plugin_larkuser.model import UserData
from ..nonebot_plugin_larkuser.utils.user import get_user
from ..nonebot_plugin_larkutils.user import get_user_id
from .lang import lang
from .utils import is_user_registered

register = on_command("register")


@register.handle()
async def _(state: T_State, user_id: str = get_user_id()) -> None:
    if await is_user_registered(user_id):
        await lang.finish("command.registered", user_id)
    await lang.send("command.tip", user_id)
    await asyncio.sleep(5)
    await lang.send("input.g", user_id)


@register.got("gender")
async def _(state: T_State, gender: str = ArgPlainText(), user_id: str = get_user_id()) -> None:
    if gender == "cancel":
        await lang.finish("command.cancel", user_id)
    if gender.lower() == "m":
        state["gender"] = True
    elif gender.lower() == "f":
        state["gender"] = False
    else:
        await register.reject(await lang.text("command.invalid", user_id))
    await lang.send("input.s", user_id)


@register.got("ship_code")
async def _(state: T_State, ship_code: str = ArgPlainText(), user_id: str = get_user_id()) -> None:
    if ship_code == "cancel":
        await lang.finish("command.cancel", user_id)
    session = get_scoped_session()
    if session.scalar(select(UserData).where(UserData.ship_code == ship_code)) is None:
        await register.reject(await lang.text("command.invalid", user_id))
    if len(ship_code) >= 25:
        await register.reject(await lang.text("command.invalid", user_id))
    state["ship_code"] = ship_code
    await lang.send(
        "input.c",
        user_id,
        user_id,
        await lang.text("gender.male" if state["gender"] else "gender.female", user_id),
        state["ship_code"],
    )


@register.got("confirm")
async def _(state: T_State, confirm: str = ArgPlainText(), user_id: str = get_user_id()) -> None:
    if confirm.lower() in ["cancel", "n"]:
        await lang.finish("command.cancel", user_id)
    session = get_scoped_session()
    user_data = await get_user(user_id, session)
    user_data.ship_code = state["ship_code"]
    user_data.gender = state["gender"]
    user_data.register_time = datetime.now()
    await lang.send("command.confirm", user_id, user_data.nickname)
    await session.commit()
    await register.finish()
