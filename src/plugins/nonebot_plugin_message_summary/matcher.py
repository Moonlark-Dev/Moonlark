from nonebot import on_message, on_command, logger
from nonebot.typing import T_State
from nonebot.adapters import Event, Bot, Message
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.params import CommandArg
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, Args, UniMessage, Reply
from nonebot_plugin_orm import async_scoped_session, get_session
from sqlalchemy import select
from typing import Literal, Sequence
from datetime import datetime, timedelta

from nonebot_plugin_larkutils import get_user_id, get_group_id, open_file, FileType
from nonebot_plugin_larkutils.file import FileManager
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_chat.utils.group import parse_message_to_string
from nonebot_plugin_chat.models import ChatGroup
from nonebot_plugin_broadcast import get_available_groups

from .models import GroupMessage
from .lang import lang
from .ai_utils import (
    fetch_broadcast_summary,
    fetch_default_summary,
    fetch_topic_summary,
    get_catgirl_score,
    analyze_debate,
    generate_message_string,
    generate_semantic_search_payload,
    analyze_history,
)
from .render_utils import (
    render_summary_result,
    render_neko_result,
    render_debate_result,
    render_history_check_result,
)

# --- Matchers ---

summary = on_alconna(
    Alconna(
        "summary",
        Subcommand("--enable|-e"),
        Subcommand("--disable|-d"),
        Subcommand("--everyday-summary", Args["status", Literal["on", "off"]]),
        Args["limit", int, 200],
        Subcommand("-s|--style", Args["style_type", Literal["default", "broadcast", "bc", "topic"], "default"]),
    )
)

recorder = on_message(priority=3, block=False)
neko_finder = on_alconna(Alconna("neko-finder"))
debate_helper = on_alconna(Alconna("debate-helper", Args["limit", int, 200]))
check_history = on_command("check-history", aliases={"发过了吗"})


# --- Config Helpers ---

def get_config() -> FileManager:
    return open_file("disabled_groups.json", FileType.CONFIG, [])

def get_everyday_summary_config() -> FileManager:
    """Get the config file for everyday summary feature"""
    return open_file("everyday_summary_config.json", FileType.CONFIG, [])


# --- Handlers ---

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
    async with get_config() as conf:
        if group_id in conf.data:
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
    
    messages = await generate_message_string(result, style)
    
    if style in ["broadcast", "bc"]:
        summary_string = await fetch_broadcast_summary(user_id, messages)
        await summary.finish(summary_string)
    elif style == "topic":
        summary_string = await fetch_topic_summary(user_id, messages)
        await summary.finish(await render_summary_result(summary_string, "topic"))
    else:
        summary_string = await fetch_default_summary(user_id, messages)
        await summary.finish(await render_summary_result(summary_string, "default"))


@summary.assign("enable")
async def _(bot: Bot, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if isinstance(bot, Bot_QQ):
        await lang.finish("switch.unsupported", user_id)
    async with get_config() as conf:
        if group_id in conf.data:
            conf.data.remove(group_id)
    await lang.finish("switch.enable", user_id)


@summary.assign("disable")
async def _(user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    async with get_config() as conf:
        if group_id not in conf.data:
            conf.data.append(group_id)
    await lang.finish("switch.disable", user_id)


@summary.assign("everyday-summary")
async def _(status: str, bot: Bot, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if isinstance(bot, Bot_QQ):
        await lang.finish("switch.unsupported", user_id)
    everyday_config = get_everyday_summary_config()
    async with everyday_config as conf:
        if status == "on":
            if group_id not in conf.data:
                conf.data.append(group_id)
            await lang.finish("everyday_summary.enable", user_id)
        else:
            if group_id in conf.data:
                conf.data.remove(group_id)
            await lang.finish("everyday_summary.disable", user_id)


@neko_finder.handle()
async def handle_neko_finder(
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """处理 .neko-finder 指令"""
    result = (
        await session.scalars(select(GroupMessage).where(GroupMessage.group_id == group_id).order_by(GroupMessage.id_))
    ).all()
    messages = await generate_message_string(list(result), "broadcast")
    catgirl_scores = await get_catgirl_score(messages)
    await neko_finder.finish(await render_neko_result(catgirl_scores, user_id))


@debate_helper.handle()
async def handle_debate(
    limit: int,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """处理 .debate 指令"""
    async with get_config() as conf:
        if group_id in conf.data:
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
    messages = await generate_message_string(result, "broadcast")
    debate_data = await analyze_debate(messages, user_id)

    if debate_data is None:
        await lang.finish("debate.no_conflict", user_id)

    await debate_helper.finish(await render_debate_result(debate_data, user_id))


@check_history.handle()
async def handle_check_history(
    bot: Bot,
    event: Event,
    session: async_scoped_session,
    state: T_State,
    args: Message = CommandArg(),
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """处理 .check-history 指令"""
    
    # 1. Input Parsing & Validation
    target_content = ""
    
    # Check for reply first
    uni_msg = UniMessage.of(args)
    await uni_msg.attach_reply(event, bot)
    if uni_msg.has(Reply):
        reply = uni_msg[Reply, 0]
        target_content = await parse_message_to_string(UniMessage([reply]), event, bot, state)
    
    # If no reply content, check arguments
    if not target_content:
        target_content = args.extract_plain_text().strip()
    
    if not target_content:
        await lang.finish("check_history.no_content", user_id)

    # 2. Stage 1: Intent Extraction
    payload = await generate_semantic_search_payload(target_content)
    
    # 3. Stage 2: Historical Analysis
    # Fetch last 48 hours of messages
    start_time = datetime.now() - timedelta(hours=48)
    history = (
        await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.timestamp >= start_time)
            .order_by(GroupMessage.id_)
        )
    ).all()
    
    if not history:
        await lang.finish("check_history.no_history", user_id)

    result = await analyze_history(payload, list(history), user_id)
    
    # 4. Visualization & Output
    if not result:
        await lang.finish("check_history.no_match", user_id)
    
    msg = await render_history_check_result(result, user_id)
    await check_history.finish(await msg.export(bot))


# --- Recorder Logic ---

async def clean_recorded_message(session: async_scoped_session) -> None:
    end_time = datetime.now() - timedelta(days=2)
    # Bulk delete is more efficient
    # await session.execute(delete(GroupMessage).where(GroupMessage.timestamp < end_time))
    # But keeping original logic structure for safety unless refactoring DB logic entirely
    for item in await session.scalars(select(GroupMessage).where(GroupMessage.timestamp < end_time)):
        await session.delete(item)

@recorder.handle()
async def _(
    event: GroupMessageEvent, session: async_scoped_session, bot: Bot, state: T_State, group_id: str = get_group_id()
) -> None:
    async with get_config() as conf:
        if group_id in conf.data:
            await recorder.finish()
    await clean_recorded_message(session)
    if (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled:
        uni_msg = UniMessage.of(event.message, bot)
        await uni_msg.attach_reply(event, bot)
        msg = await parse_message_to_string(uni_msg, event, bot, state)
    else:
        msg = event.raw_message
    session.add(GroupMessage(message=msg, sender_nickname=event.sender.nickname, group_id=group_id))
    await session.commit()
    await recorder.finish()


@recorder.handle()
async def _(
    event: Event, session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()
) -> None:
    async with get_config() as conf:
        if group_id in conf.data:
            await recorder.finish()
    await clean_recorded_message(session)
    session.add(
        GroupMessage(
            message=event.get_plaintext(), sender_nickname=(await get_user(user_id)).get_nickname(), group_id=group_id
        )
    )
    await session.commit()
