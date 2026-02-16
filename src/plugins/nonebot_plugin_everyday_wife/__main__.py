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

from nonebot import on_command
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from datetime import date
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v12 import Bot as OneBotV12Bot
from nonebot.adapters.qq import Bot as QQBot
from typing import cast, Optional
from nonebot.matcher import Matcher
from nonebot.adapters import Event, Bot, Message
from nonebot.params import CommandArg
from nonebot_plugin_session import SessionId, SessionIdType
from nonebot_plugin_larkutils import get_user_id, is_private_message
from nonebot_plugin_chat.core.session import post_group_event
from nonebot_plugin_userinfo import get_user_info


from .models import WifeData
from .utils.control import marry, divorce, get_at_argument
from .utils.init import (
    get_members_onebot_v11,
    get_members_onebot_v12,
    get_members_qq,
    match_user_with_available,
)

lang = LangHelper()


async def get_group_members(bot: Bot, group_id: str) -> list[str]:
    """根据 Bot 类型获取群成员列表"""
    if isinstance(bot, OneBotV11Bot):
        return await get_members_onebot_v11(bot, group_id)
    elif isinstance(bot, OneBotV12Bot):
        return await get_members_onebot_v12(bot, group_id)
    elif isinstance(bot, QQBot):
        return await get_members_qq(bot, group_id)
    return []


@on_command("wife", aliases={"today-wife", "waifu"}).handle()
async def _(
    matcher: Matcher,
    event: Event,
    session: async_scoped_session,
    bot: Bot,
    user_id: str = get_user_id(),
    adapter_group_id: str = SessionId(
        SessionIdType.GROUP, include_bot_type=False, include_bot_id=False, include_platform=False
    ),
    group_id: str = get_group_id(),
    arg_message: Message = CommandArg(),
    is_c2c: bool = is_private_message(),
) -> None:
    if is_c2c:
        await lang.finish("unsupported", user_id)
    argv = arg_message.extract_plain_text().strip().lower()
    platform_user_id = event.get_user_id()

    if argv == "divorce":
        await divorce(adapter_group_id, session, platform_user_id)
        await lang.finish("divorce", user_id, at_sender=True, reply_message=True)
    elif argv.startswith("force-marry"):
        target = get_at_argument(arg_message)
        if target is None:
            await lang.finish("no_target", user_id, at_sender=True, reply_message=True)
        await divorce(adapter_group_id, session, platform_user_id)
        await divorce(adapter_group_id, session, target)
        await marry((platform_user_id, target), adapter_group_id)
        await lang.finish("force_success", user_id, at_sender=True, reply_message=True)

    # 检查用户今天是否已有匹配
    query = cast(
        Optional[WifeData],
        await session.scalar(
            select(WifeData).where(
                WifeData.user_id == platform_user_id,
                WifeData.group_id == adapter_group_id,
                WifeData.generate_date == date.today(),
            )
        ),
    )

    # 如果尚未匹配，则进行按需匹配
    if query is None:
        members = await get_group_members(bot, adapter_group_id)
        matched_id = await match_user_with_available(platform_user_id, adapter_group_id, members)

        if matched_id is None:
            await lang.finish("unmatched", user_id, at_sender=True)

        # 重新查询以获取新创建的匹配记录
        query = cast(
            Optional[WifeData],
            await session.scalar(
                select(WifeData).where(
                    WifeData.user_id == platform_user_id,
                    WifeData.group_id == adapter_group_id,
                    WifeData.generate_date == date.today(),
                )
            ),
        )

        if query is None:
            await lang.finish("unmatched", user_id, at_sender=True)

    user_info = await get_user_info(bot, event, query.wife_id)
    message = UniMessage().text(text=await lang.text("matched", user_id)).at(user_id=query.wife_id)
    if user_info is not None and user_info.user_avatar:
        message = message.image(url=user_info.user_avatar.get_url())
    if query.queried:
        message = message.text(text=await lang.text("queried", user_id))
    query.queried = True
    await post_group_event(
        group_id,
        await lang.text(
            "chat_event.matched",
            user_id,
            await get_nickname(user_id, bot, event),
            await get_nickname(query.wife_id, bot, event),
        ),
        "none",
    )
    await session.commit()
    await matcher.finish(await message.export(), reply_message=True)
