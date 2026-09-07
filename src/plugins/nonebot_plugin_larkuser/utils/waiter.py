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

from typing import Optional, Callable, TypeVar
from nonebot_plugin_alconna import UniMessage
from nonebot.adapters import Event
from ..lang import lang
from ..exceptions import PromptRetryTooMuch, PromptTimeout
from .waiter2 import WaitUserInput

T = TypeVar("T")


async def prompt(
    message: str | UniMessage,
    user_id: str,
    checker: Optional[Callable[[str], bool]] = None,
    retry: int = -1,
    timeout: int = 5 * 60,
    parser: Callable[[str], T] = lambda msg: msg,
    ignore_error_details: bool = True,
    allow_quit: bool = True,
    event: Optional[Event] = None,
    events: Optional[list[Event]] = None,
) -> T:
    """等待用户输入并返回解析后的结果。

    :param event: 本次等待回复所针对的事件（如 QQ 官方机器人长会话中用户的最新消息事件）。
    :param events: 可选输出参数；若传入列表，则等待结束后其中第一个元素为收到的最新事件。
    """
    if retry == 0:
        if ignore_error_details:
            await lang.finish("prompt.retry_too_much", user_id)
        else:
            raise PromptRetryTooMuch
    waiter = WaitUserInput(message if isinstance(message, UniMessage) else UniMessage(message), user_id, event=event)
    try:
        await waiter.wait(timeout=timeout, auto_finish=False)
    except TimeoutError:
        if ignore_error_details:
            await waiter.finish("prompt.timeout")
        else:
            raise PromptTimeout
    if events is not None and waiter.get_event() is not None:
        events[:] = [waiter.get_event()]
    text = waiter.get()
    if allow_quit and text.lower() == "q":
        await waiter.finish("prompt.quited")
    if checker is not None and not checker(text):
        return await prompt(
            await lang.text("prompt.unknown", user_id),
            user_id,
            checker,
            retry - 1,
            timeout,
            parser,
            ignore_error_details,
            allow_quit,
            event=waiter.get_event() or event,
            events=events,
        )
    return parser(text)
