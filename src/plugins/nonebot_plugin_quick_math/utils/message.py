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

import asyncio

from nonebot_plugin_alconna import UniMessage

from nonebot_plugin_larkuser import prompt
from nonebot_plugin_larkuser.exceptions import PromptTimeout
from nonebot_plugin_quick_math.__main__ import lang, quick_math
from nonebot_plugin_quick_math.config import config
from nonebot_plugin_quick_math.types import QuestionData, ReplyType


async def wait_answer(question: QuestionData, image: UniMessage, user_id: str) -> ReplyType:
    message = image
    for i in range(config.qm_retry_count + 1):
        try:
            r: str = await prompt(message, user_id, timeout=question["limit_in_sec"])
        except PromptTimeout:
            return ReplyType.TIMEOUT
        if r.lower() in ["skip", "tg"]:
            return ReplyType.SKIP
        elif await question["question"]["answer"](r):
            return ReplyType.RIGHT
        message = UniMessage.text(await lang.text(f"answer.wrong", user_id, config.qm_retry_count - i))
    return ReplyType.WRONG


async def send_start_timer() -> None:
    for sec in range(config.qm_wait_time):
        await quick_math.send(str(config.qm_wait_time - sec))
        await asyncio.sleep(1)
