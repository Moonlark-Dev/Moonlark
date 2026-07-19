from datetime import datetime

from nonebot import on_message, on_notice
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import (
    Bot as OB11Bot,
    GroupRecallNoticeEvent,
    Message as OB11Message,
    MessageSegment as OB11MessageSegment,
    NoticeEvent,
)
from nonebot.adapters.onebot.v11.event import FriendRecallNoticeEvent, PokeNotifyEvent
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage, get_target
from nonebot_plugin_larkuser import get_nickname, get_user
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_larkutils.subaccount import get_main_account
from nonebot_plugin_message_summary.hash_utils import compute_message_hash
from nonebot_plugin_message_summary.models import GroupMessage
from nonebot_plugin_openai import check_ai_enabled
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..config import config
from ..models import PrivateChatSession
from ..utils.gift_drop import handle_gift_drop
from ..utils.group import enabled_group, enabled_private_chat
from .ego import moonlark_main
from .session import create_group_session, create_private_session, get_session_directly


async def record_private_chat_session(user_id: str, session_key: str, bot_id: str) -> None:
    """记录用户私聊会话信息

    Args:
        user_id: 用户 ID
        session_key: 带 platform 前缀的 session key
        bot_id: Bot ID
    """
    async with get_session() as session:
        chat_session = PrivateChatSession(
            user_id=user_id,
            session_key=session_key,
            bot_id=bot_id,
            last_message_time=datetime.now().timestamp(),
        )
        await session.merge(chat_session)
        await session.commit()


@on_message(priority=50, rule=enabled_group, block=False).handle()
async def _(
    event: Event,
    matcher: Matcher,
    bot: Bot,
    state: T_State,
    user_id: str = get_user_id(),
    session_id: str = get_group_id(),
    ai_enabled: bool = check_ai_enabled(),
) -> None:
    if not ai_enabled:
        await matcher.finish()
    target = get_target(event)
    session = await create_group_session(session_id, target, bot)
    session.set_target(target, bot)
    if session.mute_until is not None:
        await matcher.finish()
    plaintext = event.get_plaintext().strip()
    if any([plaintext.startswith(p) for p in config.command_start]):
        await matcher.finish()
    platform_message = event.get_message()
    message = await UniMessage.of(message=platform_message, bot=bot).attach_reply(event, bot)
    nickname = await get_nickname(user_id, bot, event)
    platform_user_id = event.get_user_id()
    await session.handle_message(message, user_id, event, state, nickname, event.is_tome(), platform_user_id=platform_user_id)

    # 礼物掉落检测
    try:
        await handle_gift_drop(bot, event, user_id, session_id, session.is_napcat_bot())
    except Exception as e:
        logger.exception(e)


@on_message(priority=50, rule=enabled_private_chat, block=False).handle()
async def _(
    event: Event,
    matcher: Matcher,
    bot: Bot,
    state: T_State,
    user_id: str = get_user_id(),
    session_key: str = get_group_id(),
    ai_enabled: bool = check_ai_enabled(),
) -> None:
    if not ai_enabled:
        await matcher.finish()

    # 记录私聊会话信息（用于主动消息时获取正确的 bot）
    await record_private_chat_session(user_id, session_key, bot.self_id)

    # 检查是否是主动私聊的回复
    await moonlark_main.on_private_message_replied(user_id)

    target = get_target(event)
    session = await create_private_session(session_key, target, bot)
    session.set_target(target, bot)
    if session.mute_until is not None:
        await matcher.finish()
    plaintext = event.get_plaintext().strip()
    if any([plaintext.startswith(p) for p in config.command_start]):
        # TODO 避免与 cave 冲突
        await matcher.finish()
    platform_message = event.get_message()
    message = await UniMessage.of(message=platform_message, bot=bot).attach_reply(event, bot)
    nickname = await get_nickname(user_id, bot, event)
    platform_user_id = event.get_user_id()
    await session.handle_message(message, user_id, event, state, nickname, True, platform_user_id=platform_user_id)


@on_notice(block=False).handle()
async def _(event: GroupRecallNoticeEvent, group_id: str = get_group_id()) -> None:
    message_id = str(event.message_id)
    try:
        session = get_session_directly(group_id)
    except KeyError:
        return
    await session.handle_recall(message_id)


@on_notice(block=False).handle()
async def _(
    event: PokeNotifyEvent,
    bot: Bot,
    moonlark_group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    if event.group_id is not None:
        session = await create_group_session(moonlark_group_id, get_target(event), bot)
    else:
        session = await create_private_session(user_id, get_target(event), bot)
    nickname = await get_nickname(user_id, bot, event)
    await session.handle_poke(event, nickname)


async def group_msg_emoji_like(event: NoticeEvent) -> bool:
    logger.info(result := event.notice_type == "group_msg_emoji_like")
    return result


@on_notice(rule=group_msg_emoji_like, block=False).handle()
async def _(event: NoticeEvent, bot: OB11Bot, platform_id: str = get_group_id()) -> None:
    event_dict = event.model_dump()
    group_id = f"{platform_id}_{event_dict['group_id']}"
    user_id = await get_main_account(str(event_dict["user_id"]))
    session = await create_group_session(group_id, get_target(event), bot)
    raw_msg = (await bot.get_msg(message_id=event_dict["message_id"]))["message"]
    ob11_msg = OB11Message()
    for seg in raw_msg:
        ob11_msg.append(OB11MessageSegment(**seg))
    msg_hash = compute_message_hash(ob11_msg)
    async with get_session() as db_session:
        result = await db_session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.message_hash == msg_hash)
            .limit(1),
        )
        cached = result.first()
        message = (
            cached.message
            if cached is not None
            else "".join(seg["data"].get("text", "") for seg in raw_msg if seg["type"] == "text")
        )
    user = await get_user(user_id)
    if user.has_nickname():
        operator_nickname = user.nickname
    else:
        user_info = await bot.get_group_member_info(group_id=event_dict["group_id"], user_id=int(user_id))
        operator_nickname = user_info["card"] or user_info["nickname"]
    emoji_id = event_dict["likes"][0]["emoji_id"]
    logger.debug(f"emoji like: {emoji_id} {message} {operator_nickname}")
    await session.processor.handle_reaction(message, operator_nickname, emoji_id)


@on_notice(block=False).handle()
async def _(
    bot: Bot,
    event: FriendRecallNoticeEvent,
    user_id: str = get_user_id(),
    session_key: str = get_group_id(),
) -> None:
    message_id = str(event.message_id)
    session = await create_private_session(session_key, get_target(event), bot)
    await session.handle_recall(message_id)
