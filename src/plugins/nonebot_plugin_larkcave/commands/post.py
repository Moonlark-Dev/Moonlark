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

from typing import cast
from nonebot_plugin_alconna import Arparma, Image, Reference, Text, UniMessage
from nonebot.adapters import Event
from nonebot.adapters import Bot
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_larkcave.__main__ import cave
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_larkcave.utils.post import post_cave


@cave.assign("add.content")
async def _(
    session: async_scoped_session, event: Event, bot: Bot, state: T_State, result: Arparma, user_id: str = get_user_id()
) -> None:
    try:
        content = cast(list[Image | Text], list(result.subcommands["add"].args["content"]))
    except KeyError:
        await lang.finish("add.empty", user_id)
        return
    await post_cave(content, user_id, event, bot, state, session)

from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters.onebot.v11.message import MessageSegment as OB11Segment
from nonebot.adapters.onebot.v11.message import Message as OB11Message


@cave.assign("add-node.node_msg")
async def _(
    session: async_scoped_session, node_msg: Reference, event: Event, bot: Bot, state: T_State, user_id: str = get_user_id()
) -> None:
    content = []
    if node_msg.id is None or not isinstance(bot, OB11Bot):
        await lang.finish("node.unsupported", user_id)
    try:
        node_messages = (await bot.get_forward_msg(id=node_msg.id))["messages"]
    except Exception:
        await lang.finish("node.read_failed", user_id)
    # 检查是否来自同一用户
    if len(node_messages) == 0:
        await lang.finish("node.invalid", user_id)
    if any([msg["sender"]["user_id"] != node_messages[0]["sender"]["user_id"] for msg in node_messages]):
        await lang.finish("node.check_failed_1", user_id)
    for msg in node_messages:
        message = OB11Message()
        for segment in node_messages["message"]:
            segment = OB11Segment(**segment)
            message.append(segment)
        uni_msg = UniMessage.generate_without_reply(message=message)
        if not all([isinstance(seg, Image) or isinstance(seg, Text) for seg in uni_msg]):
            await lang.finish("node.check_failed_2", user_id)
        content.append(uni_msg)
        content.append(Text("\n"))
    content.pop(-1)
    await post_cave(content, user_id, event, bot, state, session)


