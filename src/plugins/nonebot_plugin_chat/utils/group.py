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

import re
import traceback

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_openai import fetch_message, generate_message
from nonebot_plugin_openai.utils.message import get_message
from nonebot_plugin_orm import get_session
from openai import APITimeoutError

from ..lang import lang
from ..models import ChatGroup, PrivateChatConfig
from .message import parse_message_to_string as _parse_message_to_string
from .tools.browser import browser_tool


async def group_message(event: Event) -> bool:
    try:
        return event.get_user_id() != event.get_session_id()
    except (ValueError, NotImplementedError):
        return False


async def enabled_group(event: Event, group_id: str = get_group_id()) -> bool:
    async with get_session() as session:
        return bool(
            (await group_message(event)) and (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled,
        )


async def enabled_private_chat(event: Event, user_id: str = get_user_id()) -> bool:
    try:
        if event.get_user_id() == event.get_session_id():
            return await get_private_chat_enabled(user_id)
    except (ValueError, NotImplementedError):
        pass
    # QQ adapter C2C messages: get_user_id() returns openid, get_session_id() returns "friend_{openid}"
    if event.__class__.__module__.startswith("nonebot.adapters.qq"):
        from nonebot.adapters.qq.event import C2CMessageCreateEvent

        if isinstance(event, C2CMessageCreateEvent):
            return await get_private_chat_enabled(user_id)
    return False


async def get_private_chat_enabled(user_id: str) -> bool:
    """私聊 Chat 开关，未创建过配置的用户默认开启"""
    async with get_session() as session:
        g = await session.get(PrivateChatConfig, {"user_id": user_id})
        return g.enabled if g is not None else True


class BrowserErrorOccurred(Exception):
    pass


def _is_client_error(status_code: object) -> bool:
    """HTTP 4xx（客户端错误）：多半是 URL 被消息里的标点带脏了，值得修一次再试"""
    return isinstance(status_code, int) and 400 <= status_code < 500


class LinkParser:
    def __init__(self, message: str, lang_str: str) -> None:
        self.message = message
        self.lang_str = lang_str
        self.pattern = re.compile(
            r"((https?|ftp):\/\/)?(([\w\-]+\.)+[a-zA-Z]{2,}|localhost|(\d{1,3}\.){3}\d{1,3})(:\d{2,5})?(\/[^\s]*)?",
        )
        self.links = self.get_links()

    def get_links(self) -> list[re.Match[str]]:
        return [
            i
            for i in self.pattern.finditer(self.message)
            if "bilibili.com" not in i.group().lower() and "b23.tv" not in i.group().lower()
        ]

    async def parse(self) -> str:
        for link_match in self.get_links()[::-1]:
            link = link_match.group()
            try:
                description = await self.get_description(link)
                self.message = (
                    f"{self.message[: link_match.start()]}{link}({description}){self.message[link_match.end() :]}"
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
        status_code = result["metadata"].get("status_code")
        if _is_client_error(status_code) and link.endswith(")") and len(link) > 1:
            # 群消息里常见的 Markdown 写法 ``[标题](https://example.com/a)`` 会让链接
            # 正则把收尾的半角右括号一起吞进 URL，服务端因此返回 4xx。去掉这个括号
            # 再试一次：只有真的拿到 200 才采用重试结果，否则仍报告原来的错误。
            trimmed_link = link[:-1]
            logger.debug(f"链接以 ')' 结尾且返回 HTTP {status_code}，去掉括号重试: {trimmed_link}")
            retry_result = await browser_tool.browse(trimmed_link)
            retry_status_code = retry_result["metadata"].get("status_code") if retry_result["success"] else None
            if retry_status_code == 200:
                result, status_code = retry_result, retry_status_code
        if status_code != 200:
            return f"HTTP {status_code}"
        return await fetch_message(
            [
                await get_message("system", "link_parser.md.jinja"),
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


async def parse_message_to_string(
    message: UniMessage, event: Event, bot: Bot, state: T_State, lang_str: str, forward_depth: int = 0
) -> str:
    return await LinkParser(
        await _parse_message_to_string(message, event, bot, state, lang_str, forward_depth=forward_depth), lang_str
    ).parse()
