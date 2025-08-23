#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
import base64
import hashlib
import traceback

from nonebot import Bot, logger
from nonebot.internal.adapter import Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import Image, image_fetch

from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot import get_driver

from ..lang import lang
from .cache import AsyncCache

image_cache: AsyncCache


@get_driver().on_startup
async def _() -> None:
    global image_cache
    image_cache = AsyncCache(600)


async def get_image_summary(segment: Image, event: Event, bot: Bot, state: T_State) -> str:
    if not isinstance(image := await image_fetch(event, bot, state, segment), bytes):
        return "暂无信息"
    img_hash = hashlib.sha256(image).hexdigest()
    if (cache := await image_cache.get(img_hash)) is not None:
        return cache
    image_base64 = base64.b64encode(image).decode("utf-8")
    messages = [
        generate_message(await lang.text("prompt_group.image_describe_system", event.get_user_id()), "system"),
        generate_message(
            [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": await lang.text("prompt_group.image_describe_user", event.get_user_id())},
            ],
            "user",
        ),
    ]

    try:
        summary = (
            await fetch_message(
                messages,
                model="google/gemini-2.5-flash",
                extra_headers={
                    "X-Title": "Moonlark - Image Describe",
                    "HTTP-Referer": "https://image.moonlark.itcdt.top",
                },
            )
        ).strip()
        await image_cache.set(img_hash, summary)
        return summary
    except Exception:
        logger.warning(traceback.format_exc())
        return "暂无信息"
