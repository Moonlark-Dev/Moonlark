from datetime import datetime

from nonebot_plugin_alconna import UniMessage

from nonebot import logger, on_command
from nonebot.params import ArgPlainText
from nonebot.typing import T_State
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..nonebot_plugin_preview.preview import screenshot
from ..nonebot_plugin_larkuser.models import UserData
from nonebot.exception import ActionFailed
from ..nonebot_plugin_larkutils.user import get_user_id
from .lang import lang
from src.plugins.nonebot_plugin_larkuser.user.utils import is_user_registered
import traceback
from nonebot.log import logger
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

register = on_command("register")


@register.handle()
async def _(user_id: str = get_user_id()) -> None:
    if await is_user_registered(user_id):
        await lang.finish("command.registered", user_id)
    try:
        await lang.send("command.tip", user_id)
    except ActionFailed:
        logger.warning("发送最终许可协议 URL 失败，尝试以截图形式发送")
        try:
            await UniMessage().text(await lang.text("command.tip_without_url", user_id)).image(
                raw=await screenshot("https://github.com/orgs/Moonlark-Dev/discussions/3", 1), name="image.png"
            ).send()
        except Exception:
            await lang.send("command.tip_failed_to_send_content", user_id)
            logger.error(f"以截图形式发送 EUAL 失败: {traceback.format_exc()}")
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
    logger.debug(f"{ship_code=}")
    if ship_code == "cancel":
        await lang.finish("command.cancel", user_id)
    async with get_session() as session:
        if await session.scalar(select(UserData).where(UserData.ship_code == ship_code)) is not None:
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
async def _(
    state: T_State, confirm: str = ArgPlainText(), user_id: str = get_user_id(), user: UserInfo = EventUserInfo()
) -> None:
    logger.debug(f"{confirm=}")
    logger.debug(f"{state=}")
    if confirm.lower() in ["cancel", "n"]:
        await lang.finish("command.cancel", user_id)
    async with get_session() as session:
        user_data = await session.get(UserData, user_id)
        if user_data is None:
            user_data = UserData(user_id=user.user_id, nickname=user.user_name)
        user_data.ship_code = state["ship_code"]
        user_data.gender = state["gender"]
        user_data.register_time = datetime.now()
        await lang.send("command.confirm", user_id, user_data.nickname)
        await session.merge(user_data)
        await session.commit()
    await register.finish()
