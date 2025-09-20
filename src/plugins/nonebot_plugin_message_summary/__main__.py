import aiofiles
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import get_user
from sqlalchemy import select
from nonebot.adapters import Event, Bot
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot import on_message
import json
from datetime import datetime, timedelta, timezone
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, Args, UniMessage
from typing import Literal
from nonebot_plugin_openai import fetch_message, generate_message
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_localstore import get_cache_file

from .models import GroupMessage

lang = LangHelper()
summary = on_alconna(
    Alconna(
        "summary",
        Subcommand("--enable|-e"),
        Subcommand("--disable|-d"),
        Args["limit", int, 200],
        Subcommand("-s|--style", Args["style_type", Literal["default", "broadcast", "bc", "topic"], "default"]),
    )
)
config_file = get_cache_file("nonebot-plugin-message-summary", "config.json")
recorder = on_message(priority=3, block=False)


async def get_config() -> list[str]:
    if not config_file.is_file():
        return []
    async with aiofiles.open(config_file, "r") as f:
        return json.loads(await f.read())


@summary.assign("style")
async def _(
    limit: int,
    style_type: str,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    await handle_main(limit, session, style_type, user_id, group_id)


@summary.assign("$main")
async def handle_main(
    limit: int,
    session: async_scoped_session,
    style_type: str = "default",
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    style = style_type
    if group_id not in await get_config():
        await lang.finish("disabled", user_id)
    result = (
        await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .order_by(GroupMessage.id_.desc())
            .limit(limit)
            .order_by(GroupMessage.id_)
        )
    ).all()
    messages = ""
    for message in result[::-1]:
        if style in ["broadcast", "bc"]:
            # Format timestamp to include both date and time for broadcast style
            timestamp_str = message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            messages += f"[{timestamp_str}] [{message.sender_nickname}] {message.message}\n"
        else:
            messages += f"[{message.sender_nickname}] {message.message}\n"
    if style in ["broadcast", "bc"]:
        time_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        summary_string = await fetch_message(
            [
                generate_message(await lang.text("prompt2s", user_id, time_str), "system"),
                generate_message(await lang.text("prompt2u", user_id, messages), "user"),
            ],
            identify="Message Summary (Boardcast)",
        )
        await summary.finish(summary_string)
    elif style == "topic":
        summary_string = await fetch_message(
            [generate_message(await lang.text("prompt_topic", user_id), "system"), generate_message(messages, "user")],
            identify="Message Summary (Topic)",
        )
        await summary.finish(UniMessage().image(raw=await md_to_pic(summary_string)))
    else:
        summary_string = await fetch_message(
            [generate_message(await lang.text("prompt", user_id), "system"), generate_message(messages, "user")],
            identify="Message Summary",
        )
        await summary.finish(UniMessage().image(raw=await md_to_pic(summary_string)))


async def clean_recorded_message(session: async_scoped_session) -> None:
    end_time = datetime.now() - timedelta(days=2)
    for item in await session.scalars(select(GroupMessage).where(GroupMessage.timestamp < end_time)):
        await session.delete(item)


@recorder.handle()
async def _(event: GroupMessageEvent, session: async_scoped_session, group_id: str = get_group_id()) -> None:

    if group_id not in await get_config():
        await recorder.finish()
    await clean_recorded_message(session)
    session.add(GroupMessage(message=event.raw_message, sender_nickname=event.sender.nickname, group_id=group_id))
    await session.commit()
    await recorder.finish()


@recorder.handle()
async def _(
    event: Event, session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()
) -> None:
    if group_id not in await get_config():
        await recorder.finish()
    await clean_recorded_message(session)
    session.add(
        GroupMessage(
            message=event.get_plaintext(), sender_nickname=(await get_user(user_id)).get_nickname(), group_id=group_id
        )
    )
    await session.commit()


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
