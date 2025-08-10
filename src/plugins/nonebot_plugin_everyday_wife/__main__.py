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
from nonebot_plugin_userinfo import get_user_info


from .models import WifeData
from .utils.control import marry, divorce, get_at_argument
from .utils.init import init_onebot_v11_group, init_onebot_v12_group, init_qq_group

lang = LangHelper()


@on_command("wife", aliases={"today-wife", "waifu"}).handle()
async def _(
    matcher: Matcher,
    event: Event,
    session: async_scoped_session,
    bot: Bot,
    user_id: str = get_user_id(),
    group_id: str = SessionId(
        SessionIdType.GROUP, include_bot_type=False, include_bot_id=False, include_platform=False
    ),
    arg_message: Message = CommandArg(),
    is_c2c: bool = is_private_message(),
) -> None:
    if is_c2c:
        await lang.finish("unsupported", user_id)
    argv = arg_message.extract_plain_text().strip().lower()
    if isinstance(bot, OneBotV11Bot):
        await init_onebot_v11_group(bot, group_id)
    elif isinstance(bot, OneBotV12Bot):
        await init_onebot_v12_group(bot, group_id)
    elif isinstance(bot, QQBot):
        await init_qq_group(bot, group_id)
    platform_user_id = event.get_user_id()
    if argv == "divorce":
        await divorce(group_id, session, platform_user_id)
        await lang.finish("divorce", user_id, at_sender=True, reply_message=True)
    elif argv.startswith("force-marry"):
        target = get_at_argument(arg_message)
        if target is None:
            await lang.finish("no_target", user_id, at_sender=True, reply_message=True)
        await divorce(group_id, session, platform_user_id)
        await divorce(group_id, session, target)
        await marry((platform_user_id, target), group_id)
        await lang.finish("force_success", user_id, at_sender=True, reply_message=True)

    query = cast(
        Optional[WifeData],
        await session.scalar(
            select(WifeData).where(
                WifeData.user_id == platform_user_id,
                WifeData.group_id == group_id,
                WifeData.generate_date == date.today(),
            )
        ),
    )
    if query is None:
        await lang.finish("unmatched", user_id, at_sender=True)
    user_info = await get_user_info(bot, event, query.wife_id)
    message = UniMessage().text(text=await lang.text("matched", user_id)).at(user_id=query.wife_id)
    if user_info.user_avatar:
        message = message.image(url=user_info.user_avatar.get_url())
    if query.queried:
        message = message.text(text=await lang.text("queried", user_id))
    query.queried = True
    await session.commit()
    await matcher.finish(await message.export(), reply_message=True)
