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

from nonebot import on_command
from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_waiter import prompt_until

cmd = on_command("wtfis")
lang = LangHelper()


@cmd.handle()
async def _(user_id: str = get_user_id()) -> None:
    await cmd.finish(
        await fetch_message(
            [generate_message(await lang.text("prompt", user_id), "user")],
        )
    )
