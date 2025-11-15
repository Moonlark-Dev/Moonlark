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

from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot_plugin_userinfo import get_user_info
from nonebot_plugin_alconna import Image, UniMessage, Text, At, Reply, Reference
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot.adapters import Message

from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot


from ..models import ChatGroup
from .image import get_image_summary


async def group_message(event: Event) -> bool:
    return event.get_user_id() != event.get_session_id()


async def enabled_group(
    event: Event, group_id: str = get_group_id(), user_id: str = get_user_id()
) -> bool:
    async with get_session() as session:
        return bool(
            (await group_message(event)) and (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled
        )


async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
    str_msg = ""
    for segment in message:
        if isinstance(segment, Text):
            str_msg += segment.text
        elif isinstance(segment, At):
            user = await get_user(segment.target)
            if (not user.has_nickname()) and (user_info := await get_user_info(bot, event, segment.target)):
                nickname = user_info.user_displayname or user_info.user_name
            else:
                nickname = user.get_nickname()
            str_msg += f"@{nickname}"
        elif isinstance(segment, Image):
            str_msg += f"[图片: {await get_image_summary(segment, event, bot, state)}]"
        elif isinstance(segment, Reply) and segment.msg is not None:
            if isinstance(segment.msg, UniMessage):
                str_msg += f"[回复: {await parse_message_to_string(segment.msg, event, bot, state)}]"
            elif isinstance(segment.msg, Message):
                str_msg += f"[回复: {await parse_message_to_string(UniMessage.generate_without_reply(message=segment.msg), event, bot, state)}]"
            else:
                str_msg += f"[回复: {segment.msg}]"
        elif isinstance(segment, Reference) and isinstance(bot, OneBotV11Bot) and segment.id is not None:
            str_msg += f"[合并转发: {segment.id}]"
        else:
            str_msg += f"[特殊消息: {segment.dump()}]"
    return str_msg


# from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot
# from nonebot.matcher import Matcher

# @on_message().handle()
# async def _(matcher: Matcher, event: GroupMessageEvent, bot: Bot, state: T_State):
#     if event.group_id == 598443695:
#         message = UniMessage.of(event.get_message())
#         await message.attach_reply()
#         await matcher.finish(await parse_message_to_string(message, event, bot, state))
