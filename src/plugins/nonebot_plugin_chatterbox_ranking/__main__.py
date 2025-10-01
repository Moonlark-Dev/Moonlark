from typing import Literal
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils.file import FileType
from sqlalchemy import select
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot import on_message
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, UniMessage, Args, At
from nonebot_plugin_larkutils import get_user_id, get_group_id, open_file
from .image import render_bar
from .lang import lang
from .models import GroupChatterbox, GroupChatterboxWithNickname

chatterbox = on_alconna(
    Alconna(
        "chatterbox", Subcommand("--enable|-e"), Subcommand("--disable|-d"), Args["user_id_arg?", Literal["me"] | At]
    ),
    aliases={"ct"},
)

recorder = on_message(priority=3, block=False)


@chatterbox.assign("user_id")
async def _(
    session: async_scoped_session,
    user_id_arg: Literal["me"] | At = "me",
    sender_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
            await lang.finish("disabled", sender_id)
    if user_id_arg == "me":
        user_id = sender_id
    else:
        user_id = user_id_arg.target
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


@chatterbox.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
            await lang.finish("disabled", user_id)
    result = (
        await session.scalars(
            select(GroupChatterbox)
            .where(GroupChatterbox.group_id == group_id)
            .order_by(GroupChatterbox.message_count.desc())
            .limit(12)
        )
    ).all()
    await chatterbox.finish(
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


@recorder.handle()
async def _(session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
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


@chatterbox.assign("enable")
async def _(bot: Bot, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if isinstance(bot, Bot_QQ):
        await lang.finish("switch.unsupported", user_id)
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id not in f.data:
            f.data.append(group_id)
    await lang.finish("switch.enable", user_id)


@chatterbox.assign("disable")
async def _(user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
            f.data.pop(f.data.index(group_id))
    await lang.finish("switch.disable", user_id)
