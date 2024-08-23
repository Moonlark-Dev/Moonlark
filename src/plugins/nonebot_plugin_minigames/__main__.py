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

from pathlib import Path
import aiofiles
import json
from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args, Match, UniMessage
from src.plugins.nonebot_plugin_larklang import LangHelper
from src.plugins.nonebot_plugin_larkutils import get_user_id
from src.plugins.nonebot_plugin_ranking import generate_image
from src.plugins.nonebot_plugin_render import render_template
from src.plugins.nonebot_plugin_bag.utils.give import give_item_by_data
from .plugins.nonebot_plugin_minigames_api import get_user_data, exchange_pawcoin, get_rank_user

alc = Alconna("minigame", Subcommand("rank"), Subcommand("exchange", Args["count?", int]), Subcommand("me"))
matcher = on_alconna(alc)
lang = LangHelper()


@matcher.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    async with aiofiles.open(Path(__file__).parent.joinpath("minigames.json"), encoding="utf-8") as f:
        content = await f.read()
    data = json.loads(content)
    image = await render_template(
        "help.html.jinja",
        await lang.text("command.help_title", user_id),
        user_id,
        {
            "commands": [
                {
                    "description": await lang.text(f"{item['id']}.description", user_id),
                    "details": await lang.text(f"{item['id']}.details", user_id),
                    "name": item["name"],
                    "usages": [
                        await LangHelper("nonebot_plugin_larkhelp").text(
                            "list.usage", user_id, await lang.text(f"{item['id']}.usage{c + 1}", user_id)
                        )
                        for c in range(item["usage"])
                    ],
                }
                for item in data
            ],
            "usage_text": await LangHelper("nonebot_plugin_larkhelp").text("list.usage_text", user_id),
        },
    )


@matcher.assign("me")
async def _(user_id: str = get_user_id()) -> None:
    user = await get_user_data(user_id)
    await lang.finish(
        "command.me_info",
        user_id,
        user.total_points,
        user.count,
        user.seconds,
        user.exchanged_pawcoin,
        user.get_exchangeable_pawcoin() + user.exchanged_pawcoin,
    )


@matcher.assign("rank")
async def _(user_id: str = get_user_id()) -> None:
    image = await generate_image(
        sorted([u async for u in get_rank_user()], key=lambda x: x["data"], reverse=True),
        user_id,
        await lang.text("command.ranking_title", user_id),
    )
    await matcher.finish(UniMessage().image(raw=image))


@matcher.assign("exchange")
async def _(count: Match[int], user_id: str = get_user_id()) -> None:
    user = await get_user_data(user_id)
    exchangeable = user.get_exchangeable_pawcoin()
    if count.available and not 0 < count.result < exchangeable:
        await lang.finish("command.exchange_not_enough", user_id, exchangeable)
    count = count.result if count.available else exchangeable
    await exchange_pawcoin(user_id, count)
    await give_item_by_data(
        user_id,
        {"experience": 0, "vimcoin": 0, "items": [{"item_id": "moonlark:pawcoin", "count": count, "data": {}}]},
    )
    await lang.finish("command.exchange_success", user_id, count)
