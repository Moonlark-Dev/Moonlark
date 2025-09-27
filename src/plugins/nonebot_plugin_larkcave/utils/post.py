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

import asyncio
from datetime import datetime
from typing import NoReturn, cast

from nonebot import Bot
from nonebot.internal.adapter import Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import Image, Text, UniMessage, image_fetch

from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select, func

from ..__main__ import cave
from ..exceptions import ReviewFailed, EmptyImage, DuplicateCave
from ..lang import lang

from ..models import CaveData
from .checker import check_cave
from .decoder import decode_cave
from .encoder import encode_text, encode_image

lock = asyncio.Lock()


async def get_cave_id(session: async_scoped_session) -> int:
    result = await session.scalar(select(func.max(CaveData.id)))
    return (result + 1) if result is not None else 0


async def post_cave(
    content: list[Image | Text], user_id: str, event: Event, bot: Bot, state: T_State, session: async_scoped_session
) -> NoReturn:
    await lang.send("add.checking", user_id)
    try:
        await check_cave(content, event, bot, state, session)
    except ReviewFailed as e:
        await lang.finish("add.review_fail", user_id, e.reason)
    except EmptyImage:
        await lang.finish("add.image_empty", user_id)
    except DuplicateCave as e:
        msg = UniMessage(await lang.text("add.similarity_title", user_id))
        msg.extend(await decode_cave(e.cave, session, user_id))
        msg.append(Text(await lang.text("add.similarity_footer", user_id, round(e.score * 100, 3))))
        await cave.finish(msg, reply_message=True)
    async with lock:
        cave_id = await get_cave_id(session)
        content = " ".join(
            [
                (
                    (await encode_text(seg.text))
                    if isinstance(seg, Text)
                    else (
                        await encode_image(
                            cave_id, seg.name, cast(bytes, await image_fetch(event, bot, state, seg)), session
                        )
                    )
                )
                for seg in content
            ]
        )
        session.add(CaveData(id=cave_id, author=user_id, time=datetime.now(), content=content))
        await session.commit()
    await lang.finish("add.posted", user_id, cave_id)
