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

from nonebot import on_message
from ..lang import lang
from typing import Optional, Callable, TypeVar
from nonebot.matcher import Matcher
import asyncio
from nonebot_plugin_alconna import UniMessage
from datetime import datetime
from nonebot.adapters import Event, Bot
from nonebot_plugin_larkutils import get_user_id

T = TypeVar("T")


class Waiter:
    """支持富文本的等待用户输入对象。

    实现方式与原有的纯文本等待器一致：为等待者注册一个独立的 ``on_message``
    事件响应器，在 ``wait`` 中轮询直到收到通过 ``checker`` 检查的输入或超时。
    与纯文本版本不同的是，``checker`` 与 ``parser`` 的输入均为
    :class:`nonebot_plugin_alconna.UniMessage`，因此图片等富文本内容不会被丢弃。
    """

    def __init__(
        self,
        prompt_text: UniMessage,
        user_id: str,
        checker: Optional[Callable[[UniMessage], bool]] = None,
        default: Optional[UniMessage] = None,
    ) -> None:
        self.prompt_text = prompt_text
        self.user_id = user_id
        self.default = default
        self.checker = checker or (lambda _: True)
        self.answer: Optional[UniMessage] = None
        self.message_matcher = on_message(block=True, rule=self.check_user)
        self.message_matcher.handle()(self.handle_message)

    async def check_user(self, user_id: str = get_user_id()) -> bool:
        return user_id == self.user_id

    async def handle_message(self, matcher: Matcher, event: Event, bot: Bot, user_id: str = get_user_id()) -> None:
        message = UniMessage.generate_without_reply(event=event, bot=bot)
        try:
            result = self.checker(message)
        except Exception:
            result = False
        if not result:
            await lang.send("prompt.unknown", user_id, at_sender=False, reply_message=True, matcher=matcher)
            return
        self.answer = message

    async def wait(self, timeout: int = 210, auto_finish: bool = True) -> None:
        await self.prompt_text.send()
        start_time = datetime.now()
        while self.answer is None and (datetime.now() - start_time).total_seconds() <= timeout:
            await asyncio.sleep(0.1)
        try:
            if self.answer is None:
                if self.default is not None:
                    self.answer = self.default
                elif auto_finish:
                    await lang.finish("prompt.timeout", self.user_id, at_sender=False, reply_message=True)
                else:
                    raise TimeoutError
        finally:
            try:
                self.message_matcher.destroy()
            except (IndexError, ValueError):
                pass

    def get(self, parser: Callable[[UniMessage], T] = lambda message: message) -> T:
        if self.answer is not None:
            return parser(self.answer)
        raise ValueError("No input!")


class WaitUserInput(Waiter):
    """以消息纯文本为输入的等待用户输入对象。

    由支持富文本的 :class:`Waiter` 实现：``checker`` 与 ``parser`` 收到的
    是用户输入经 ``UniMessage.extract_plain_text()`` 提取后的纯文本，
    以保持与旧版 ``WaitUserInput`` 相同的接口行为。
    """

    def __init__(
        self,
        prompt_text: UniMessage,
        user_id: str,
        checker: Optional[Callable[[str], bool]] = None,
        default: Optional[str] = None,
    ) -> None:
        super().__init__(
            prompt_text=prompt_text,
            user_id=user_id,
            checker=self.wrap_text_checker(checker),
            default=UniMessage(default) if isinstance(default, str) else default,
        )

    @staticmethod
    def wrap_text_checker(checker: Optional[Callable[[str], bool]]) -> Callable[[UniMessage], bool]:
        """将纯文本检查器包装为 UniMessage 检查器"""

        def check_message(message: UniMessage) -> bool:
            text_checker = checker or (lambda _: True)
            return text_checker(message.extract_plain_text())

        return check_message

    def get(self, parser: Callable[[str], T] = lambda message: message) -> T:
        return super().get(lambda message: parser(message.extract_plain_text()))
