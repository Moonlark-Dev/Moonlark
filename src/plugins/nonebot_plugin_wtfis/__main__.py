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

from nonebot_plugin_alconna import Alconna, Args, Image, MultiVar, Option, Subcommand, Text, on_alconna
from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.adapters import Bot as BaseBot

lang = LangHelper()
wtfis = on_alconna(
    Alconna(
        "wtfis",
        Args["topic", str, ""]
    ), 
    use_cmd_start=True
)


@wtfis.assign("$main")
async def _(bot: BaseBot, topic: str, user_id: str = get_user_id()) -> None:
    if isinstance(bot, BotQQ):
        await lang.send("llm_tip", user_id)
        topic = ""
    await wtfis.finish(
        await fetch_message(
            [
                generate_message(await lang.text("prompt", user_id), "system"),
                generate_message(topic, "user")
            ] 
            if topic else [generate_message(await lang.text("prompt", user_id), "user")],
            identify="wtfis"
        )
    )
