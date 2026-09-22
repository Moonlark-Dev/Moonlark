#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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

import json
import traceback
from datetime import datetime
from typing import Optional

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq.bot import Bot as QQBot
from nonebot.exception import ActionFailed
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_userinfo import UserInfo
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot_plugin_larkutils import review_text
from nonebot_plugin_preview.preview import screenshot

from .waiter import prompt
from ..exceptions import PromptTimeout
from ..lang import lang
from ..models import UserData
from ..user.utils import is_user_registered


async def send_eula_screenshot(user_id: str) -> None:
    try:
        await UniMessage().text(await lang.text("command.tip_without_url", user_id)).image(
            raw=await screenshot("https://github.com/orgs/Moonlark-Dev/discussions/3", 1),
            name="image.png",
        ).send()
    except Exception:
        await lang.send("command.tip_failed_to_send_content", user_id)
        logger.error(f"以截图形式发送 EUAL 失败: {traceback.format_exc()}")


NICKNAME_MAX_LENGTH = 27
NICKNAME_PROMPT_ATTEMPTS = 3


def default_nickname(user_id: str) -> str:
    """返回用户未提供昵称时使用的兜底昵称。

    ``UserData.nickname`` 是非空列，任何情况下都不能写入 ``NULL``，
    因此注册流程统一使用 ``用户-{user_id}`` 兜底，与
    :meth:`nonebot_plugin_larkuser.user.registered.MoonlarkRegisteredUser.setup_user`
    中的展示兜底保持一致。
    """
    return f"用户-{user_id}"


async def get_nickname(user: UserInfo, user_id: str, event: Optional[Event] = None) -> tuple[str, bool]:
    """获取注册流程使用的昵称。

    :return: ``(昵称, 是否锁定昵称)``。昵称一定非空：用户留空 / 发送 ``q``、
    昵称审查连续不通过或等待超时时，回退为 :func:`default_nickname`。
    """
    if user.user_name and (platform_nickname := user.user_name.strip()):
        return platform_nickname, False
    fallback = default_nickname(user_id)
    prompt_text = await lang.text("input.user_nickname", user_id, user_id)
    events: list[Event] = []
    for _ in range(NICKNAME_PROMPT_ATTEMPTS):
        try:
            nickname = (
                await prompt(
                    prompt_text,
                    user_id,
                    checker=lambda msg: len(msg) <= NICKNAME_MAX_LENGTH,
                    ignore_error_details=False,
                    allow_quit=False,
                    event=event,
                    events=events,
                )
            ).strip()
        except PromptTimeout:
            await lang.send("input.nickname_failed", user_id)
            return fallback, False
        if events:
            event = events[-1]
        # 提示文案允许用户发送 “q” 或直接留空来表示不设置昵称
        if not nickname or nickname.lower() == "q":
            return fallback, False
        review_result = await review_text(nickname)
        if review_result["conclusion"]:
            return nickname, True
        prompt_text = await lang.text("input.nickname_review_failed", user_id, review_result["message"])
    await lang.send("input.nickname_failed", user_id)
    return fallback, False


async def register_user(
    session: AsyncSession | async_scoped_session,
    user_id: str,
    user: UserInfo,
    bot: Bot | None = None,
    event: Optional[Event] = None,
) -> str:
    if await is_user_registered(user_id):
        await lang.finish("command.registered", user_id)
    try:
        await lang.send("command.tip", user_id)
    except ActionFailed:
        logger.warning("发送最终许可协议 URL 失败，尝试以截图形式发送")
        await send_eula_screenshot(user_id)
    if isinstance(bot, QQBot):
        confirm_msg = (
            UniMessage()
            .style(
                await lang.text("command.confirm_eula_markdown", user_id),
                "markdown",
            )
            .keyboard(
                Button("enter", await lang.text("command.button_yes", user_id), text="y"),
                Button("enter", await lang.text("command.button_no", user_id), text="n"),
            )
        )
    else:
        confirm_msg = await lang.text("command.confirm_eula", user_id)
    events: list[Event] = []
    if not await prompt(
        confirm_msg,
        user_id,
        parser=lambda t: t.strip().lower().startswith("y"),
        event=event,
        events=events,
    ):
        await lang.finish("command.cancel", user_id)
    if events:
        event = events[-1]
    nickname, lock_nickname = await get_nickname(user, user_id, event)
    # 兜底保护：nickname 是 NOT NULL 列，写入 None 会触发
    # IntegrityError: Column 'nickname' cannot be null
    if not (nickname := (nickname or "").strip()):
        nickname, lock_nickname = default_nickname(user_id), False
    u = UserData(
        user_id=user_id,
        nickname=nickname,
        register_time=datetime.now(),
        config=json.dumps({"lock_nickname": lock_nickname}),
    )
    await session.merge(u)
    await session.commit()
    return nickname
