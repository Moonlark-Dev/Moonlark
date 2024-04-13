import random
from sqlalchemy import select
from .model import CaveData
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Image,
    MultiVar,
    Subcommand,
    on_alconna,
    Text,
    Image
)
from .decoder import decode_cave
from nonebot_plugin_orm import async_scoped_session
from typing import Union
from ..nonebot_plugin_larkutils import get_user_id, get_group_id
from .lang import lang
from sqlalchemy.exc import NoResultFound
from .cool_down import (
    is_group_cooled,
    on_group_use
)


alc = Alconna(
    "cave",
    Subcommand(
        "a|add",
        Args["content", MultiVar(Union[Image, Text])], # type: ignore
    ),
    Subcommand(
        "s|restore",
        Args["cave_id", int],
    ),
    Subcommand(
        "g|get",
        Args["cave_id", int],
    ),
    Subcommand(
        "r|remove",
        Args["cave_id", int],
    ),
    separators="-"
)
cave = on_alconna(
    alc,
    use_cmd_start=True,
    skip_for_unmatch=False
)

async def get_cave(session: async_scoped_session) -> CaveData:
    cave_id_list = (await session.scalars(select(CaveData.id).where(CaveData.public))).all()
    cave_id = random.choice(cave_id_list)
    return await session.get_one(CaveData, {"id": cave_id})


@cave.assign("$main")
async def _(
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id()
) -> None:
    if not (group_cd_data := await is_group_cooled(group_id, session))[0]:
        await lang.finish("cave.group_cd", user_id, round(group_cd_data[1] / 60, 3))
    try:
        cave_data = await get_cave(session)
        content = await decode_cave(cave_data, session, user_id)
    except NoResultFound:
        await lang.finish("cave.noresult", user_id)
        raise
    except IndexError:
        await lang.finish("cave.nocave", user_id)
        raise
    await on_group_use(group_id, session)
    await cave.finish(content)