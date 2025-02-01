import random
from typing import Union
from nonebot import on_fullmatch
from nonebot_plugin_alconna import Alconna, Args, Image, MultiVar, Option, Subcommand, Text, on_alconna
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_schedule.utils import complete_schedule
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from nonebot.exception import ActionFailed


from nonebot_plugin_larkutils import get_group_id, get_user_id
from .cool_down import is_group_cooled, is_user_cooled, on_use
from .decoder import decode_cave
from .lang import lang
from .models import CaveData
from .plugins.comment.get import get_comments
from .plugins.comment.message import add_cave_message

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
    separators=["-", " "],
)
cave = on_alconna(alc, use_cmd_start=True, skip_for_unmatch=False)


async def get_cave(session: async_scoped_session) -> CaveData:
    cave_id_list = (await session.scalars(select(CaveData.id).where(CaveData.public))).all()
    cave_id = random.choice(cave_id_list)
    return await session.get_one(CaveData, {"id": cave_id})


async def send_cave(session: async_scoped_session, user_id: str, group_id: str, reverse: bool = False) -> None:
    try:
        cave_data = await get_cave(session)
        cave_id = cave_data.id
        content = await decode_cave(cave_data, session, user_id, cave_id == 398 or reverse)
    except NoResultFound:
        await lang.finish("cave.noresult", user_id)
        raise
    except IndexError:
        await lang.finish("cave.nocave", user_id)
        raise
    cave_message = await content.send()
    if msg := await get_comments(cave_id, session, user_id):
        await msg.send()
    await on_use(group_id, user_id, session)
    try:
        add_cave_message(cave_id, str(cave_message.msg_ids[0]["message_id"]))
    except TypeError:
        # Ignore exception mentioned in issue 325, which is caused by f**king QQ
        pass


async def handle_get_cave(
    session: async_scoped_session, user_id: str = get_user_id(), group_id: str = get_group_id(), reverse: bool = False
) -> None:
    if not (user_cd_data := await is_user_cooled(user_id, session))[0]:
        await lang.finish("cave.user_cd", user_id, round(user_cd_data[1] / 60, 3))
    if not (group_cd_data := await is_group_cooled(group_id, session))[0]:
        await lang.finish("cave.group_cd", user_id, round(group_cd_data[1] / 60, 3))
    for _ in range(3):
        try:
            await send_cave(session, user_id, group_id, reverse)
        except ActionFailed:
            continue
        break
    else:
        await lang.finish("failed_to_send", user_id)
    await cave.finish()


@cave.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    await complete_schedule(user_id, "cave")
    await handle_get_cave(session, user_id, group_id, False)


@on_fullmatch("evac\\").handle()
async def _(session: async_scoped_session, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    await handle_get_cave(session, user_id, group_id, True)
