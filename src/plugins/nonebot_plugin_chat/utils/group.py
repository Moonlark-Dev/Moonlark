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

import re
from .tools.browser import browser_tool, generate_page_info
from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import get_session
from .message import parse_message_to_string as _parse_message_to_string
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_openai import generate_message, fetch_message


from ..models import ChatGroup


async def group_message(event: Event) -> bool:
    return event.get_user_id() != event.get_session_id()


async def enabled_group(event: Event, group_id: str = get_group_id(), user_id: str = get_user_id()) -> bool:
    async with get_session() as session:
        return bool(
            (await group_message(event)) and (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled
        )


class BrowserErrorOccurred(Exception):
    pass


class LinkParser:
    def __init__(self, message: str) -> None:
        self.message = message
        self.pattern = re.compile(
            r"((https?|ftp):\/\/)?(([\w\-]+\.)+[a-zA-Z]{2,}|localhost|(\d{1,3}\.){3}\d{1,3})(:\d{2,5})?(\/[^\s]*)?"
        )
        self.links = self.get_links()

    def get_links(self) -> list[re.Match[str]]:
        return [i for i in self.pattern.finditer(self.message)]

    async def parse(self) -> str:
        for link_match in self.get_links()[::-1]:
            link = link_match.group()
            description = await self.get_description(link)
            self.message = f"{self.message[:link_match.start()]}{link}({description}){self.message[link_match.end():]}"
        return self.message

    @staticmethod
    async def get_description(link: str) -> str:
        page_markdown = await browser_tool.browse(link)
        if page_markdown["success"]:
            raise BrowserErrorOccurred(f"解析失败: {page_markdown['error']}")
        return await fetch_message(
            [
                generate_message(
                    (
                        "接下来我会向你发送一个网页的内容，你需要为这个网页生成一条简介。\n"
                        "简介只能包含一行，不能包含 Markdown 格式。\n"
                        "你的回复中不能出现除了该页面的简介以外的任何内容。"
                    ),
                    "system",
                ),
                generate_message(generate_page_info(page_markdown), "user"),
            ],
            identify="Link Parse",
        )


async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
    return await LinkParser(await _parse_message_to_string(message, event, bot, state)).parse()
