#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

from nonebot_plugin_waiter import prompt as waiter_prompt
from typing import Optional, Callable, TypeVar
from nonebot_plugin_alconna import UniMessage
from datetime import datetime
from ..lang import lang
from ..exceptions import PromptRetryTooMuch, PromptTimeout

T = TypeVar("T")


async def prompt(
        message: str | UniMessage,
        user_id: str,
        checker: Optional[Callable[[str], bool]] = None,
        retry: int = -1,
        timeout: int = 5 * 60,
        parser: Callable[[str], T] = lambda msg: msg,
        ignore_error_details: bool = True,
        allow_quit: bool = True
) -> T:
    if retry == 0:
        if ignore_error_details:
            await lang.finish("prompt.retry_too_much", user_id)
        else:
            raise PromptRetryTooMuch
    resp = await waiter_prompt(message, timeout=timeout)
    if resp is None:
        if ignore_error_details:
            await lang.finish("prompt.timeout", user_id)
        else:
            raise PromptTimeout
    text = resp.extract_plain_text()
    if text.lower() == "q":
        await lang.finish("prompt.quited", user_id)
    if not checker(text):
        return await prompt(
            await lang.text("prompt.unknown", user_id),
            user_id,
            checker,
            retry - 1,
            timeout,
            parser,
            ignore_error_details
        )
    return parser(text)






