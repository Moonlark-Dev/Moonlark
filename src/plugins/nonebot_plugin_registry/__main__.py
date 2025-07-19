import base64
import json
from datetime import datetime

from nonebot_plugin_alconna import UniMessage

from nonebot.adapters import Message
from nonebot import logger, on_command
from nonebot.params import ArgPlainText, CommandArg
from nonebot.typing import T_State
from typing import Optional
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from nonebot_plugin_email.utils.send import send_email

from nonebot_plugin_preview.preview import screenshot
from nonebot_plugin_larkuser.models import UserData
from nonebot_plugin_larkuser.exceptions import PromptTimeout
from nonebot_plugin_larkuser.utils.base58 import base58_decode
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.utils.waiter import prompt
from nonebot.exception import ActionFailed

from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_larkutils import review_text
from .lang import lang
from nonebot_plugin_larkuser.user.utils import is_user_registered
import traceback
from nonebot.log import logger
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

register = on_command("register")


async def send_eula_screenshot(user_id: str) -> None:
    try:
        await UniMessage().text(await lang.text("command.tip_without_url", user_id)).image(
            raw=await screenshot("https://github.com/orgs/Moonlark-Dev/discussions/3", 1), name="image.png"
        ).send()
    except Exception:
        await lang.send("command.tip_failed_to_send_content", user_id)
        logger.error(f"以截图形式发送 EUAL 失败: {traceback.format_exc()}")

async def get_nickname(user: UserInfo, user_id: str) -> tuple[Optional[str], bool]:
    if user.user_displayname:
        return user.user_displayname, False
    prompt_text = await lang.text("prompt.user_nickname", user_id, user_id)
    for i in range(3):
        try:
            nickname = await prompt(prompt_text, user_id, checker=lambda msg: len(msg) <= 27, ignore_error_details=False, allow_quit=False)
        except PromptTimeout:
            return None, False
        review_result = await review_text(nickname)
        if review_result["conclusion"]:
            return nickname, True
        prompt_text = await lang.text("prompt.nickname_review_failed", user_id, review_result["message"])
    await lang.text("prompt.nickname_failed", user_id)
    return None, False



@register.handle()
async def _(session: async_scoped_session, message: Message = CommandArg(), user: UserInfo = EventUserInfo(), user_id: str = get_user_id()) -> None:
    invite_user = None
    if text := message.extract_plain_text():
        if await is_user_registered(user := base58_decode(text)):
            invite_user = user
        else:
            await lang.finish("invite.unknown", user_id)
    if await is_user_registered(user_id):
        await lang.finish("command.registered", user_id)
    try:
        await lang.send("command.tip", user_id)
    except ActionFailed:
        logger.warning("发送最终许可协议 URL 失败，尝试以截图形式发送")
        await send_eula_screenshot(user_id)
    if not await prompt(await lang.text("command.confirm_eula", user_id), user_id, parser=lambda t: t.strip().lower().startswith("y")):
        await lang.finish("command.cancel", user_id)
    u = UserData(
        user_id=user_id,
        nickname=(d := await get_nickname(user, user_id))[0],
        register_time=datetime.now(),
        config=base64.b64encode(json.dumps({"lock_nickname": d[1]}).encode("utf-8"))
    )
    await session.merge(u)
    await session.commit()
    await lang.finish("welcome", user_id, d[0] or f"用户-{user_id}")



async def gain_invite(user_id: str, invited_user_id: str, invited_user_data: UserInfo) -> None:
    await send_email(
        [user_id],
        await lang.text("invite.inviter_email.subject", user_id),
        await lang.text("invite.inviter_email.content", user_id, invited_user_data.user_displayname or invited_user_id),
        items=[
            {"item_id": "special:vimcoin", "count": 200, "data": {}},
            {"item_id": "special:experience", "count": 10, "data": {}},
            {"item_id": "special:fav", "count": 1, "data": {}},
        ],
    )
    await send_email(
        [user_id],
        await lang.text("invite.invited_email.subject", invited_user_id),
        await lang.text("invite.invited_email.content", invited_user_id, user_id),
        items=[
            {"item_id": "special:vimcoin", "count": 30, "data": {}},
            {"item_id": "special:experience", "count": 5, "data": {}},
            {"item_id": "special:fav", "count": 7, "data": {"multiple": 1000}},  # 0.007
        ],
    )


