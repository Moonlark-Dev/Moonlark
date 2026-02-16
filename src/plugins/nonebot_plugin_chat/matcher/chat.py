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

import json

from nonebot_plugin_chat.core.session import get_session_directly, group_disable
from nonebot_plugin_chat.core.session.base import BaseSession
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.params import CommandArg

from nonebot import on_command
from nonebot.adapters import Bot, Message
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session
from nonebot.matcher import Matcher
from ..lang import lang
from ..models import ChatGroup



class CommandHandler:

    def __init__(
        self, mathcer: Matcher, bot: Bot, session: async_scoped_session, message: Message, group_id: str, user_id: str
    ):
        self.matcher = mathcer
        self.bot = bot
        self.session = session
        self.group_id = group_id
        self.user_id = user_id
        self.argv = message.extract_plain_text().split(" ")
        self.group_config = ChatGroup(group_id=self.group_id, enabled=False)

    async def setup(self) -> "CommandHandler":
        if isinstance(self.bot, BotQQ):
            await lang.finish("command.not_available", self.user_id)
        self.group_config = (await self.session.get(ChatGroup, {"group_id": self.group_id})) or ChatGroup(
            group_id=self.group_id, enabled=False
        )
        return self

    def is_group_enabled(self) -> bool:
        return self.group_config.enabled

    async def handle_switch(self) -> None:
        if self.is_group_enabled():
            await self.handle_off()
        else:
            await self.handle_on()

    async def merge_group_config(self) -> None:
        await self.session.merge(self.group_config)
        await self.session.commit()

    async def handle_off(self) -> None:
        self.group_config.enabled = False
        await self.merge_group_config()
        await group_disable(self.group_id)
        await lang.finish("command.switch.disabled", self.user_id)

    async def handle_on(self) -> None:
        self.group_config.enabled = True
        await self.merge_group_config()
        await lang.finish("command.switch.enabled", self.user_id)

    async def handle_desire(self) -> None:
        session = await self.get_group_session()
        length = session.accumulated_text_length
        probability = await session.get_probability(apply_ghot_coeefficient=False)
        await lang.send("command.desire.get", self.user_id, length, round(probability, 2), session.ghot_coefficient)

    async def handle_mute(self) -> None:
        session = await self.get_group_session()
        await session.mute()
        await lang.finish("command.mute", self.user_id)

    async def handle_unmute(self) -> None:
        session = await self.get_group_session()
        session.mute_until = None
        await lang.finish("command.unmute", self.user_id)

    async def handle_calls(self) -> None:
        session = await self.get_group_session()
        await self.matcher.finish("\n".join(session.tool_calls_history))

    async def handle_block(self) -> None:
        if len(self.argv) < 2:
            await lang.finish("command.no_argv", self.user_id)

        target_type = self.argv[1]

        if target_type == "user":
            if len(self.argv) < 3:
                await lang.finish("command.no_argv", self.user_id)
            action = self.argv[2]
            blocked_list = json.loads(self.group_config.blocked_user)

            if action == "list":
                await lang.finish("command.block.user.list", self.user_id, ", ".join(blocked_list))

            if len(self.argv) < 4:
                await lang.finish("command.no_argv", self.user_id)
            target_id = self.argv[3]

            if action == "add":
                if target_id not in blocked_list:
                    blocked_list.append(target_id)
                    self.group_config.blocked_user = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.user.added", self.user_id, target_id)
                else:
                    await lang.finish("command.block.user.exists", self.user_id, target_id)
            elif action == "remove":
                if target_id in blocked_list:
                    blocked_list.remove(target_id)
                    self.group_config.blocked_user = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.user.removed", self.user_id, target_id)
                else:
                    await lang.finish("command.block.user.not_found", self.user_id, target_id)

        elif target_type == "keyword":
            if len(self.argv) < 3:
                await lang.finish("command.no_argv", self.user_id)
            action = self.argv[2]
            blocked_list = json.loads(self.group_config.blocked_keyword)

            if action == "list":
                await lang.finish("command.block.keyword.list", self.user_id, ", ".join(blocked_list))

            if len(self.argv) < 4:
                await lang.finish("command.no_argv", self.user_id)
            target_keyword = self.argv[3]

            if action == "add":
                if target_keyword not in blocked_list:
                    blocked_list.append(target_keyword)
                    self.group_config.blocked_keyword = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.keyword.added", self.user_id, target_keyword)
                else:
                    await lang.finish("command.block.keyword.exists", self.user_id, target_keyword)
            elif action == "remove":
                if target_keyword in blocked_list:
                    blocked_list.remove(target_keyword)
                    self.group_config.blocked_keyword = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.keyword.removed", self.user_id, target_keyword)
                else:
                    await lang.finish("command.block.keyword.not_found", self.user_id, target_keyword)
        else:
            await lang.finish("command.no_argv", self.user_id)

    async def handle(self) -> None:
        match self.argv[0]:
            case "switch":
                await self.handle_switch()
            case "desire":
                await self.handle_desire()
            case "mute":
                await self.handle_mute()
            case "unmute":
                await self.handle_unmute()
            case "calls":
                await self.handle_calls()
            case "on":
                await self.handle_on()
            case "off":
                await self.handle_off()
            case "block":
                await self.handle_block()
            case _:
                await lang.finish("command.no_argv", self.user_id)

    async def get_group_session(self) -> BaseSession:
        try:
            return get_session_directly(self.group_id)
        except KeyError:
            if self.is_group_enabled():
                await lang.finish("command.not_inited", self.user_id)
            else:
                await lang.finish("command.disabled", self.user_id)


@on_command("chat").handle()
async def _(
    matcher: Matcher,
    bot: Bot,
    session: async_scoped_session,
    message: Message = CommandArg(),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    handler = CommandHandler(matcher, bot, session, message, group_id, user_id)
    await handler.setup()
    await handler.handle()

