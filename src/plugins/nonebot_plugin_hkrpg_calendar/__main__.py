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
from datetime import datetime
from typing import TypedDict

import httpx
from nonebot_plugin_alconna import UniMessage
from nonebot import on_command
from nonebot_plugin_preview.preview import screenshot
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template, generate_render_keys

from .data_source import get_events, request_takumi_api

matcher = on_command("hsr-calendar", aliases={"hsrc"})
lang = LangHelper()


@matcher.handle()
async def _(user_id: str = get_user_id()) -> None:
    takumi_api_result = await request_takumi_api()
    if takumi_api_result is None:
        await lang.finish("takumi_failed", user_id=user_id)
    image = await render_template(
        "hkrpg_calendar.html.jinja",
        await lang.text("title", user_id),
        user_id,
        {
            "wiki_info": await get_events(),
            "mhy_bbs": takumi_api_result,
            "dt": datetime.now()
        },
        keys=await generate_render_keys(lang, user_id, [f"template.{k}" for k in [
            "day",
            "card_pool.title",
            "card_pool.coming",
            "card_pool.up_at",
            "card_pool.co_running",
            "card_pool.current",
            "card_pool.open_forever",
            "card_pool.up_remain",
            "event.time_to_open",
            "event.title",
            "event.at",
            "event.coming",
            "event.after_update",
            "event.close_at",
            "event.ongoing",
            "cur_ver"
        ]])
    )
    await UniMessage().image(raw=image).send()
    await matcher.finish()
