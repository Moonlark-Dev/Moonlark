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

import asyncio
from typing import Any
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_waiter import prompt
from nonebot.compat import type_validate_python
from ...nonebot_plugin_larkuser import get_user
from ..lang import lang_text, lang, lang_define
from .models import Task, Choice
from nonebot.log import logger

class BreakError(Exception):

    def __init__(self, index: int) -> None:
        self.index = index


class IgnoredError(Exception):
    pass


class Node:

    def __init__(self, line: "Line", command: str, *args) -> None:
        self.command = command
        if self.command == "choice":
            raise IgnoredError
        self.line = line
        self.user_id = line.user_id
        self.args = args

    async def get_args(self) -> list[Any]:
        a = []
        for arg in self.args:
            if isinstance(arg, list) and len(arg) > 0:
                if isinstance(arg[0], str):
                    a.append(self.line.execute_node(arg))
                    continue
                elif isinstance(arg[0], list):
                    line = Line(arg, self.line.executor)
                    a.append(await line.execute())
                    continue
            a.append(arg)
        return a

    async def execute(self) -> Any:
        return await getattr(self, self.command)(*await self.get_args())

    async def get_character_name(self, name: str) -> str:
        return await lang_define.text(f"characters.{name}", self.user_id)

    async def get_text(self, key: str, *args, **kwargs) -> str:
        kwargs = kwargs | {"__nickname__": await self.get_user("get_nickname")}
        return await lang_text.text(f"{self.line.executor.path}.{key}", self.user_id, *args, **kwargs)

    async def info(self, key: str) -> None:
        text = await self.get_text(f"info_{key}")
        if (n := self.line.next()) and n[0] == "info":
            await lang.send("node.info", self.user_id, text)
            await asyncio.sleep(0.5)
        else:
            self.line.set_message(await lang.text("node.info", self.user_id, text))
            await self.line.send()

    async def sleep(self, sec: int) -> None:
        await asyncio.sleep(sec)

    async def say(self, name: str, key: str) -> None:
        l_name = await self.get_character_name(name)
        text = await self.get_text(f"{name}_{key}")
        if (n := self.line.next()) and n[0] == "say" and n[1] == name:
            await lang.send("node.say", self.user_id, l_name, text)
            await asyncio.sleep(0.75)
        else:
            self.line.set_message(await lang.text("node.say", self.user_id, l_name, text))
            await self.line.send()

    @staticmethod
    async def is_same(a: Any, b: Any) -> bool:
        return a == b

    async def get_user(self, attr: str, user_id: str | None = None):
        user = self.line.executor.user if user_id is None else await get_user(user_id or self.user_id)
        return getattr(user, attr)()

    async def jump(self, index: int) -> None:
        raise BreakError(index)


class Line:

    def __init__(self, line: list[list[Any]], executor: "TaskExecutor") -> None:
        self.user_id = executor.user_id
        self.executor = executor
        self.line = line
        self.index = 0
        self.message = UniMessage()

    def set_message(self, message: str | UniMessage) -> None:
        if isinstance(message, str):
            self.message = UniMessage().text(message)
        else:
            self.message = message

    async def execute(self) -> None:
        while 0 <= self.index < len(self.line):
            await self.execute_current_node()
        if self.index != len(self.line):
            raise BreakError(self.index - len(self.line) if self.index > 0 else self.index)

    async def execute_current_node(self) -> Any:
        await self.execute_node(self.line[self.index])
        self.index += 1

    async def get_choices(self) -> list[Choice]:
        n = self.next()
        if n is None:
            return []
        elif n[0] != "choice":
            return []
        choices = []
        for c in n[1:]:
            choice = type_validate_python(Choice, c)
            if choice.condition is None or self.execute_node(choice.condition):
                choices.append(choice)
        return choices

    async def get_default_choice_text(self) -> str:
        return await lang.text("executor.continue", self.user_id)

    async def get_choices_list(self, choices: list[Choice]) -> list[str]:
        choices_list = []
        length = 0
        for choice in choices:
            length += 1
            content = await lang_text.text(
                f"{self.executor.path}.choice_{choice.content}",
                self.user_id,
                __nickname__=self.executor.user.get_nickname() if self.executor.user else self.user_id,
            )
            choices_list.append(await lang.text("executor.choice", self.user_id, length, content))
        return choices_list

    async def get_input(self) -> list[list[Any]]:
        choices = await self.get_choices()
        if choices:
            message = self.message.text("".join(await self.get_choices_list(choices)))
        else:
            message = self.message.text(await self.get_default_choice_text())
        if message[0].is_text() and message[0].text.startswith("\n"):
            message[0].text = message[0].text[1:]
        i = 1
        while True:
            msg = await prompt(await message.export())
            if msg is not None and (text := msg.extract_plain_text()).isnumeric():
                if 0 < (i := int(text)) <= len(choices) or len(choices) == 0:
                    break
            message = UniMessage().text(await lang.text("executor.unknown", self.user_id))
            continue
        i -= 1
        self.set_message("")
        return choices[i].replies if len(choices) > 0 else []

    async def send(self) -> None:
        line = Line(await self.get_input(), self.executor)
        return await line.execute()

    def next(self) -> list[Any] | None:
        if self.index + 1 < len(self.line):
            return self.line[self.index + 1]

    async def execute_node(self, node_data: list[Any]) -> Any:
        try:
            return await Node(self, *node_data).execute()
        except BreakError as e:
            logger.waring(f"{traceback.format_exc()}")
            self.index += e.index
        except IgnoredError:
            logger.waring(f"{traceback.format_exc()}")
            return


class TaskExecutor:

    def __init__(self, path: str, task: Task, user_id: str) -> None:
        self.task = task
        self.user_id = user_id
        self.path = path
        self.user = None

    async def execute(self) -> None:
        self.user = await get_user(self.user_id or self.user_id)
        line = Line(self.task.story, self)
        await line.execute()
