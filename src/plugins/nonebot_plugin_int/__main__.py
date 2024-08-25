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

from nonebot_plugin_alconna import Alconna, on_alconna, Option, Args
from ..nonebot_plugin_larkutils import get_user_id
from ..nonebot_plugin_larklang import LangHelper

alc = Alconna(
    "int",
    Args["number", str],
    Args["base", int, 0],
    Option("-t", Args["to", int, 10])
)
matcher = on_alconna(alc)
lang = LangHelper()

def num_to_str(num: int) -> str:
    if num >= 10:
        return chr(65 + num - 10)
    return f"{num}"

def convert(num: int, to: int) -> str:
    if num < 0:
        return f"-{convert(abs(num), to)}"
    l = []
    while True:
        num, reminder = divmod(num, to)
        l.append(num_to_str(reminder))
        if num == 0:
            break
    return "".join(l[::-1])

@matcher.handle()
async def _(number: str, base: int, to: int, user_id: str = get_user_id()) -> None:
    if not 0 <= base <= 36:
        await lang.finish("error.wrong_arg", user_id, base)
    if not 1 <= to <= 36:
        await lang.finish("error.wrong_arg", user_id, to)
    try:
        await matcher.finish(convert(int(number, base), to))
    except ValueError as e:
        await matcher.finish(str(e))


