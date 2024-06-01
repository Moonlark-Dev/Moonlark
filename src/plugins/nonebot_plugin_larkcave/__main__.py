import random
import traceback
from typing import Union

from nonebot.log import logger
from nonebot_plugin_alconna import Alconna, Args, Image, MultiVar, Option, Subcommand, Text, on_alconna
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from ..nonebot_plugin_larkutils import get_group_id, get_user_id
from .cool_down import is_group_cooled, is_user_cooled, on_use
from .decoder import decode_cave
from .lang import lang
from .model import CaveData
from .plugins.nonebot_plugin_cave_comment.get import get_comments
from .plugins.nonebot_plugin_cave_comment.message import add_cave_message

alc = Alconna(
    "cave",
    Subcommand(
        "a|add",
        Args["content", MultiVar(Union[Image, Text])],  # type: ignore
    ),
    Subcommand(
        "s|restore",
        Args["cave_id", int],
    ),
    Subcommand(
        "g|get",
        Args["cave_id", int],
    ),
    Subcommand("r|remove", Option("-c|--comment", Args["comment_id", int]), Args["cave_id?", int]),
    Subcommand("c|cd", Option("-s|--set", Args["time", float]), Option("-u|--user")),
    separators="-",
)
cave = on_alconna(alc, use_cmd_start=True, skip_for_unmatch=False)


async def get_cave(session: async_scoped_session) -> CaveData:
    cave_id_list = (await session.scalars(select(CaveData.id).where(CaveData.public))).all()
    cave_id = random.choice(cave_id_list)
    return await session.get_one(CaveData, {"id": cave_id})


@cave.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if not (user_cd_data := await is_user_cooled(user_id, session))[0]:
        await lang.finish("cave.user_cd", user_id, round(user_cd_data[1] / 60, 3))
    if not (group_cd_data := await is_group_cooled(group_id, session))[0]:
        await lang.finish("cave.group_cd", user_id, round(group_cd_data[1] / 60, 3))
    try:
        cave_data = await get_cave(session)
        cave_id = cave_data.id
        content = await decode_cave(cave_data, session, user_id)
    except NoResultFound:
        await lang.finish("cave.noresult", user_id)
        raise
    except IndexError:
        await lang.finish("cave.nocave", user_id)
        raise
    try:
        add_cave_message(cave_id, str((await content.send()).msg_ids[0]["message_id"]))
    except Exception:
        logger.error(f"写入回声洞消息队列时发生错误: {traceback.format_exc()}")
    if msg := await get_comments(cave_id, session, user_id):
        await msg.send()
    await on_use(group_id, user_id, session)
    await cave.finish()
