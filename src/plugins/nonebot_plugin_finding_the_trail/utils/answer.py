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

import io
from nonebot.internal.adapter import Message
from nonebot_plugin_alconna import UniMessage
from typing import TYPE_CHECKING
from nonebot_plugin_waiter import prompt
from .string import get_command_list_string
from src.plugins.nonebot_plugin_finding_the_trail.__main__ import lang
from src.plugins.nonebot_plugin_finding_the_trail.exceptions import Quited
from .enums import Directions
from src.plugins.nonebot_plugin_finding_the_trail.utils.image import generate_map_image

if TYPE_CHECKING:
    from .fttmap import FttMap

DIRECTIONS_DICT = {"w": Directions.UP, "a": Directions.LEFT, "s": Directions.DOWN, "d": Directions.RIGHT}


class AnswerGetter:

    def __init__(self, user_id: str, ftt_map: "FttMap") -> None:
        self.user_id = user_id
        self.map = ftt_map
        self.next_message = ""
        self.command_list = []

    async def send(self) -> str:
        return (await prompt(self.next_message)).extract_plain_text()

    async def get_map_message(self) -> Message:
        fp = io.BytesIO()
        generate_map_image(self.map.map).save(fp, "PNG")
        message = (
            UniMessage()
            .image(raw=fp.getvalue())
            .text(await lang.text("ftt.start", self.user_id, len(self.command_list), len(self.map.answer)))
        )
        return await message.export()

    async def get_input(self) -> list[Directions]:
        msg = await self.send()
        d_list = []
        for o in list(msg):
            if o in DIRECTIONS_DICT:
                d_list.append(DIRECTIONS_DICT[o])
            elif o == "q":
                raise Quited()
            elif o == "c":
                d_list.clear()
                self.command_list.clear()
            elif o == "b":
                if len(d_list) >= 1:
                    d_list.pop(-1)
                else:
                    self.command_list.pop(-1)
        return d_list

    async def get_commands(self) -> list[Directions]:
        self.next_message = await self.get_map_message()
        while len(self.command_list) != len(self.map.answer):
            self.command_list.extend(await self.get_input())
            self.next_message = await lang.text(
                "ftt.step",
                self.user_id,
                len(self.command_list),
                len(self.map.answer),
                await get_command_list_string(self.command_list, self.user_id),
            )
        return self.command_list
