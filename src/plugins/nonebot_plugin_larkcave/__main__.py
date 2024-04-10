import random
from sqlalchemy import select
from .model import CaveData, ImageData
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Image,
    MultiVar,
    UniMessage,
    Subcommand,
    on_alconna,
    Text,
    Image
)
from .decoder import decode_cave
from nonebot_plugin_orm import async_scoped_session
from typing import Union
from ..nonebot_plugin_larkutils import get_user_id
from .lang import lang
from ..nonebot_plugin_larkuser import get_user
from sqlalchemy.exc import NoResultFound


alc = Alconna(
    "cave",
    Subcommand(
        "a|add",
        Args["content", MultiVar(Union[Image, Text])], # type: ignore
    ),
    separators="-"
)
cave = on_alconna(
    alc,
    use_cmd_start=True
)


async def get_cave(session: async_scoped_session) -> CaveData:
    cave_id_list = (await session.scalars(select(CaveData.id).where(CaveData.public))).all()
    cave_id = random.choice(cave_id_list)
    return await session.get_one(CaveData, {"id": cave_id})


@cave.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id) -> None:
    try:
        cave_data = await get_cave(session)
        content = await decode_cave(cave_data, session, user_id)
    except NoResultFound:
        await lang.finish("cave.noresult", user_id)
        raise
    except IndexError:
        await lang.finish("cave.nocave", user_id)
        raise
    await cave.finish(content)