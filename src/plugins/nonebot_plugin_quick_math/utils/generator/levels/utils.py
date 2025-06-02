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
from typing import Callable, Awaitable
from nonebot.log import logger
from nonebot_plugin_openai.utils.chat import fetch_messages
from nonebot_plugin_openai.utils.message import generate_message


def parse_int(a: int) -> str:
    num = {
        -1: "-",
        1: "",
    }.get(a, str(a))
    return f"+{num}" if a > 0 else f"{num}"


AI_PROMPT_SYSTEM = """
请判断用户输入的表达式和标准答案的表达式的内容是否相符，用户输入的表达式可能是纯文本、latex 或其他任何格式，而标准答案的表达式的格式为 latex，只要在数学上这两个输入具有同样的意义且用户输入的表达式化到了最简，那么就判断这用户的回答是相符的。
如果用户的输入和标准答案的表达式内容是相符的，你需要回答“true”，否则，回答“false”。
你的回答只能包含这两个单词中的一个。
"""
AI_PROMPT_TEMPLATE = """
标准答案：{}
用户输入：{}
"""


def get_verify_function(answer: str, user_id: str) -> Callable[[str], Awaitable[bool]]:
    logger.debug(answer)
    async def verify(string: str) -> bool:
        reply = await fetch_messages(
            [
                generate_message(AI_PROMPT_SYSTEM, "system"),
                generate_message(AI_PROMPT_TEMPLATE.format(answer, string), "user")
            ],
            user_id
        )
        return reply == "true"
    return verify
