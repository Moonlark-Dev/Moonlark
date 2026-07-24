"""
QQ Adapter Mention 用户名缓存补全模块

在 QQ 群聊消息中，当消息包含 @提及 (MentionUser) 且带有 username 字段时，
自动将被提及用户的昵称更新到 larkuser 数据中。

更新条件：
1. 被提及用户暂无昵称（nickname 为空或未设置）
2. 被提及用户的当前昵称是通过本机制设置的（config 中 nick_source == "mention"）

其他渠道（如 /setnick 命令、Recorder 自动识别）设置的昵称不会被覆盖。
"""

import json

from nonebot import on_message
from nonebot.log import logger
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound

from nonebot.adapters.qq.bot import Bot as QQBot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.adapters.qq.message import MentionUser

from .subaccount import get_main_account

# 配置键名：用于标记昵称来源
NICK_SOURCE_KEY = "nick_source"
NICK_SOURCE_MENTION = "mention"


async def _is_qq_group_message(bot) -> bool:
    """规则：仅处理 QQ Bot 适配器的群聊消息"""
    return isinstance(bot, QQBot)


mention_cache_matcher = on_message(block=False, priority=8, rule=_is_qq_group_message)


@mention_cache_matcher.handle()
async def _(
    session: async_scoped_session,
    event: GroupMessageCreateEvent,
) -> None:
    from nonebot_plugin_larkuser.models import UserData

    # 防御性检查：确保是群聊事件
    if not isinstance(event, GroupMessageCreateEvent):
        return

    message = event.get_message()
    mention_segments = message.get("mention_user")

    if not mention_segments:
        return

    for seg in mention_segments:
        if not isinstance(seg, MentionUser):
            continue

        # 跳过 Bot 用户的提及
        if seg.data.get("is_bot"):
            continue

        username = seg.data.get("username")
        mentioned_user_id = seg.data.get("user_id")

        if not username or not mentioned_user_id:
            continue

        await _update_nickname_from_mention(session, mentioned_user_id, username)


async def _update_nickname_from_mention(
    session: async_scoped_session,
    mentioned_user_id: str,
    username: str,
) -> None:
    """根据 mention 中的 username 更新被提及用户的昵称"""
    from nonebot_plugin_larkuser.models import UserData

    # 解析主账号（处理子账号映射）
    main_user_id = await get_main_account(mentioned_user_id)

    try:
        user_data = await session.get_one(UserData, {"user_id": main_user_id})
    except NoResultFound:
        logger.debug(f"被提及用户 {main_user_id} 尚未注册，跳过")
        return

    # 检查用户是否已注册（必须有 register_time）
    if not user_data.register_time:
        logger.debug(f"用户 {main_user_id} 未完成注册，跳过")
        return

    config = json.loads(user_data.config)
    nick_source = config.get(NICK_SOURCE_KEY)

    # 判断是否需要更新：无昵称 或 昵称来源于本机制
    has_existing_nickname = bool(user_data.nickname)
    if has_existing_nickname and nick_source != NICK_SOURCE_MENTION:
        logger.debug(
            f"用户 {main_user_id} 已有昵称（来源非 mention），跳过更新: "
            f"当前昵称={user_data.nickname!r}, username={username!r}"
        )
        return

    # 昵称相同，无需更新
    if user_data.nickname == username:
        logger.debug(f"用户 {main_user_id} 昵称已是 {username!r}，无需更新")
        return

    logger.info(
        f"通过 @提及 补全用户 {main_user_id} 的昵称: "
        f"{user_data.nickname!r} -> {username!r}"
    )

    user_data.nickname = username
    config[NICK_SOURCE_KEY] = NICK_SOURCE_MENTION
    user_data.config = json.dumps(config)
    await session.commit()
