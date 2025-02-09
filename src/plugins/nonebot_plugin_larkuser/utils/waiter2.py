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

from nonebot import on_message
from ..lang import lang
from nonebot_plugin_larkutils import get_user_id
from typing import Optional, Callable, TypeVar
from nonebot.matcher import Matcher
import asyncio
from nonebot_plugin_alconna import UniMessage
from datetime import datetime
from nonebot.adapters import Event

T = TypeVar("T")


class WaitUserInput:

    def __init__(
        self,
        prompt_text: UniMessage,
        user_id: str,
        checker: Optional[Callable[[str], bool]],
        default: Optional[str] = None,
    ) -> None:
        self.prompt_text = prompt_text
        self.user_id = user_id
        self.default = default
        self.checker = checker or (lambda _: True)
        self.answer = None
        self.message_matcher = on_message(block=True, rule=self.check_user)
        self.message_matcher.handle()(self.handle_message)

    async def check_user(self, user_id: str = get_user_id()):
        return user_id == self.user_id

    async def handle_message(self, matcher: Matcher, event: Event, user_id: str = get_user_id()) -> None:
        text = event.get_plaintext()
        try:
            result = self.checker(text)
        except Exception:
            result = False
        if not result:
            await lang.finish("prompt.unknown", user_id, at_sender=False, reply_message=True, matcher=matcher)
        self.answer = text

    async def wait(self, timeout: int = 210, auto_finish: bool = True) -> None:
        await self.prompt_text.send()
        start_time = datetime.now()
        while self.answer is None and (datetime.now() - start_time).total_seconds() <= timeout:
            await asyncio.sleep(0.1)
        if self.answer is None:
            if self.default is not None:
                self.answer = self.default
            elif auto_finish:
                self.message_matcher.destroy()
                await lang.finish("prompt.timeout", self.user_id, at_sender=False, reply_message=True)
            else:
                raise TimeoutError
        self.message_matcher.destroy()

    def get(self, parser: Callable[[str], T] = lambda message: message) -> T:
        if self.answer is not None:
            return parser(self.answer)
        raise ValueError("No input!")
