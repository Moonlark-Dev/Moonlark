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
import traceback

from nonebot import logger

from openai import APITimeoutError
from .tools.browser import browser_tool
from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import get_session
from .message import parse_message_to_string as _parse_message_to_string
from nonebot_plugin_larkutils import get_group_id
from nonebot_plugin_openai import generate_message, fetch_message
from ..lang import lang

from ..models import ChatGroup


async def group_message(event: Event) -> bool:
    return event.get_user_id() != event.get_session_id()


async def enabled_group(event: Event, group_id: str = get_group_id()) -> bool:
    async with get_session() as session:
        return bool(
            (await group_message(event)) and (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled
        )


class BrowserErrorOccurred(Exception):
    pass


class LinkParser:
    def __init__(self, message: str, lang_str: str) -> None:
        self.message = message
        self.lang_str = lang_str
        self.pattern = re.compile(
            r"((https?|ftp):\/\/)?(([\w\-]+\.)+[a-zA-Z]{2,}|localhost|(\d{1,3}\.){3}\d{1,3})(:\d{2,5})?(\/[^\s]*)?"
        )
        self.links = self.get_links()

    def get_links(self) -> list[re.Match[str]]:
        return [
            i
            for i in self.pattern.finditer(self.message)
            if "bilibili.com" not in i.group().lower()
            and "b23.tv" not in i.group().lower()
        ]

    async def parse(self) -> str:
        for link_match in self.get_links()[::-1]:
            link = link_match.group()
            try:
                description = await self.get_description(link)
                self.message = (
                    f"{self.message[:link_match.start()]}{link}({description}){self.message[link_match.end():]}"
                )
            except BrowserErrorOccurred:
                logger.warning(traceback.format_exc())
            except APITimeoutError:
                logger.warning(f"解析超时: {link}")
        return self.message

    async def get_description(self, link: str) -> str:
        result = await browser_tool.browse(link)
        if not result["success"]:
            raise BrowserErrorOccurred(f"解析失败: {result}")
        return await fetch_message(
            [
                generate_message(
                    await lang.text("prompt_link_parser", self.lang_str),
                    "system",
                ),
                generate_message(
                    await lang.text(
                        "browse_webpage.success",
                        self.lang_str,
                        result["url"],
                        result["metadata"]["status_code"],
                        result["metadata"]["description"],
                        result["metadata"]["keywords"],
                        result["metadata"]["content_length"],
                        result["title"],
                        result["content"],
                    ),
                    "user",
                ),
            ],
            identify="Link Parse",
            timeout=90,
        )


async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State, lang_str: str) -> str:
    return await LinkParser(await _parse_message_to_string(message, event, bot, state), lang_str).parse()
