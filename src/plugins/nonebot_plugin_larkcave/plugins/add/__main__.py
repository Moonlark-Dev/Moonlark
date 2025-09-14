import asyncio
from datetime import datetime
from typing import cast
from nonebot_plugin_alconna import Arparma, Image, Text, UniMessage, image_fetch
from sqlalchemy import select
from .exception import ReviewFailed, EmptyImage, DuplicateCave
from nonebot.adapters import Event
from nonebot.adapters import Bot
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.sql.expression import func

from ...__main__ import cave
from typing import NoReturn
from nonebot_plugin_larkutils import get_user_id
from ...models import CaveData
from ...lang import lang
from ...decoder import decode_cave
from .encoder import encode_image, encode_text
from .checker import check_cave


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


@cave.assign("add.content")
async def _(
    session: async_scoped_session, event: Event, bot: Bot, state: T_State, result: Arparma, user_id: str = get_user_id()
) -> None:
    try:
        content = cast(list[Image | Text], list(result.subcommands["add"].args["content"]))
    except KeyError:
        await lang.finish("add.empty", user_id)
        return
    await post_cave(content, user_id, event, bot, state, session)
