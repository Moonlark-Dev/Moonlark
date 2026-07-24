"""
QQ Adapter Mention 用户名缓存补全模块

在 QQ 群聊消息中，当消息包含 @提及 (MentionUser) 且带有 username 字段时，
自动将被提及用户的昵称更新到 larkuser 数据中。

更新条件：
1. 被提及用户暂无昵称（nickname 为空）
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

# 配置键名：用于标记昵称来源
NICK_SOURCE_KEY = "nick_source"
NICK_SOURCE_MENTION = "mention"


async def _is_qq_bot(bot) -> bool:
    """规则：仅处理 QQ Bot 适配器的消息"""
    return isinstance(bot, QQBot)


mention_nick_matcher = on_message(block=False, priority=3, rule=_is_qq_bot)


@mention_nick_matcher.handle()
async def _(
    session: async_scoped_session,
    bot: QQBot,
    event: GroupMessageCreateEvent,
) -> None:
    from nonebot_plugin_larkuser.models import UserData

    message = event.get_message()
    mention_segments = message.get("mention_user")

    if not mention_segments:
        return

    for seg in mention_segments:
        if not isinstance(seg, MentionUser):
            continue

        username = seg.data.get("username")
        mentioned_user_id = seg.data.get("user_id")

        if not username or not mentioned_user_id:
            continue

        try:
            user_data = await session.get_one(UserData, {"user_id": mentioned_user_id})
        except NoResultFound:
            # 被提及用户尚未注册，跳过
            continue

        config = json.loads(user_data.config)
        nick_source = config.get(NICK_SOURCE_KEY)

        # 判断是否需要更新：无昵称 或 昵称来源于本机制
        should_update = bool(not user_data.nickname or nick_source == NICK_SOURCE_MENTION)

        if not should_update:
            continue

        if user_data.nickname == username:
            # 昵称相同，无需更新
            continue

        logger.info(
            f"通过 @提及 补全用户 {mentioned_user_id} 的昵称: "
            f"'{user_data.nickname}' -> '{username}'"
        )

        user_data.nickname = username
        config[NICK_SOURCE_KEY] = NICK_SOURCE_MENTION
        user_data.config = json.dumps(config)
        await session.commit()
