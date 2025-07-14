import aiofiles
from nonebot_plugin_larkuser import get_user
from sqlalchemy import select
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot import on_message
import json
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, UniMessage, Args, At
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_localstore import get_cache_file

from .image import render_bar
from .lang import lang
from .models import GroupChatterbox, GroupChatterboxWithNickname

summary = on_alconna(
    Alconna("chatterbox", Subcommand("--enable|-e"), Subcommand("--disable|-d"), Args["user_id?", str | At]),
    aliases={"ct"},
)
config_file = get_cache_file("nonebot-plugin-chatterbox-ranking", "config.json")
recorder = on_message(priority=3, block=False)


async def get_config() -> list[str]:
    if not config_file.is_file():
        return []
    async with aiofiles.open(config_file, "r") as f:
        return json.loads(await f.read())


@summary.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if group_id not in await get_config():
        await lang.finish("disabled", user_id)
    result = (
        await session.scalars(
            select(GroupChatterbox)
            .where(GroupChatterbox.group_id == group_id)
            .order_by(GroupChatterbox.message_count.desc())
            .limit(12)
        )
    ).all()
    await summary.finish(
        UniMessage().image(
            raw=await render_bar(
                [
                    GroupChatterboxWithNickname(
                        nickname=(await get_user(data.user_id)).get_nickname(), message_count=data.message_count
                    )
                    for data in result
                ],
                user_id,
                group_id,
            )
        )
    )


@summary.assign("user_id")
async def _(
    session: async_scoped_session, user_id: str, sender_id: str = get_user_id(), group_id: str = get_group_id()
) -> None:
    if group_id not in await get_config():
        await lang.finish("disabled", user_id)
    if user_id == "me":
        user_id = sender_id
    index = 1
    for user in await session.scalars(
        select(GroupChatterbox)
        .where(GroupChatterbox.group_id == group_id)
        .order_by(GroupChatterbox.message_count.desc())
    ):
        if user.user_id == user_id:
            await lang.finish("find.result", user_id, user_id, index, user.message_count)
        index += 1
    await lang.finish("find.not_found", user_id)


@recorder.handle()
async def _(session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()) -> None:
    if group_id not in await get_config():
        await recorder.finish()
    result = await session.scalar(
        select(GroupChatterbox).where(GroupChatterbox.group_id == group_id, GroupChatterbox.user_id == user_id)
    )
    if result is None:
        result = GroupChatterbox(group_id=group_id, user_id=user_id, message_count=1)
    else:
        result.message_count += 1
    await session.merge(result)
    await session.commit()
    await recorder.finish()


@summary.assign("enable")
async def _(bot: Bot, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if isinstance(bot, Bot_QQ):
        await lang.finish("switch.unsupported", user_id)
    config = await get_config()
    if group_id not in config:
        config.append(group_id)
    async with aiofiles.open(config_file, "w") as f:
        await f.write(json.dumps(config))
    await lang.finish("switch.enable", user_id)


@summary.assign("disable")
async def _(user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    config = await get_config()
    if group_id in config:
        config.pop(config.index(group_id))
    async with aiofiles.open(config_file, "w") as f:
        await f.write(json.dumps(config))
    await lang.finish("switch.disable", user_id)
