#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

import base64
import json
import traceback
from datetime import datetime
from typing import Optional

from nonebot import logger
from nonebot.exception import ActionFailed
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_userinfo import UserInfo
from sqlalchemy.ext.asyncio import AsyncSession

from nonebot_plugin_larkuser import prompt
from nonebot_plugin_larkuser.exceptions import PromptTimeout

from nonebot_plugin_larkuser.lang import lang
from nonebot_plugin_larkuser.models import UserData
from nonebot_plugin_larkuser.user.utils import is_user_registered
from nonebot_plugin_larkutils import review_text
from nonebot_plugin_preview.preview import screenshot


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
            nickname = await prompt(
                prompt_text, user_id, checker=lambda msg: len(msg) <= 27, ignore_error_details=False, allow_quit=False
            )
        except PromptTimeout:
            return None, False
        review_result = await review_text(nickname)
        if review_result["conclusion"]:
            return nickname, True
        prompt_text = await lang.text("prompt.nickname_review_failed", user_id, review_result["message"])
    await lang.text("prompt.nickname_failed", user_id)
    return None, False


async def register_user(session: AsyncSession | async_scoped_session, user_id: str, user: UserInfo) -> str:
    if await is_user_registered(user_id):
        await lang.finish("command.registered", user_id)
    try:
        await lang.send("command.tip", user_id)
    except ActionFailed:
        logger.warning("发送最终许可协议 URL 失败，尝试以截图形式发送")
        await send_eula_screenshot(user_id)
    if not await prompt(
        await lang.text("command.confirm_eula", user_id), user_id, parser=lambda t: t.strip().lower().startswith("y")
    ):
        await lang.finish("command.cancel", user_id)
    u = UserData(
        user_id=user_id,
        nickname=(d := await get_nickname(user, user_id))[0],
        register_time=datetime.now(),
        config=base64.b64encode(json.dumps({"lock_nickname": d[1]}).encode("utf-8")),
    )
    await session.merge(u)
    await session.commit()
    return d[0]
