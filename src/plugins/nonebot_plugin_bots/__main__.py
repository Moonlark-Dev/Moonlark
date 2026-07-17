import time
from nonebot.adapters.onebot.v11.bot import Bot as V11Bot
from nonebot.adapters.onebot.v12.bot import Bot as V12Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_apscheduler import scheduler
from nonebot import logger
from nonebot.message import event_preprocessor
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException, ActionFailed
from nonebot import get_bot
from nonebot import get_app
from fastapi import FastAPI, HTTPException, Request
from typing import Optional, cast

from nonebot_plugin_larkutils import get_group_id, get_user_id
from .config import config
from .types import BotStatus, OnlineBotStatus
from .models import UserBotPrivateChatSettings, GroupBind
from .bind import try_process_bind_code

from nonebot import get_bots
from nonebot_plugin_orm import get_session

sessions: dict[str, tuple[str, float]] = {}


async def get_bot_status(user_id: str, all_fields: bool = False) -> BotStatus:
    try:
        bot = get_bot(user_id)
    except KeyError:
        if all_fields:
            return OnlineBotStatus(
                user_id=user_id,
                adapter_name="",
                online=False,
                good=False,
                nickname="",
            )
        return {"user_id": user_id, "online": False}
    try:
        if isinstance(bot, QQBot):
            good = bot.ready
            nickname = bot.self_info.username
        elif isinstance(bot, V11Bot):
            status = await bot.get_status()
            good = status.get("good", False)
            nickname = (await bot.get_login_info()).get("nickname")
        elif isinstance(bot, V12Bot):
            status = await bot.get_status()
            good = status.get("good", False)
            nickname = (await bot.get_self_info())["user_name"]
        else:
            good = False
            nickname = None
    except ActionFailed:
        good = False
        nickname = None
    return OnlineBotStatus(
        user_id=user_id,
        adapter_name=bot.adapter.get_name(),
        online=True,
        good=bool(good),
        nickname=nickname,
    )
    # {
    #     "user_id": user_id,
    #     "adapter_name": bot.adapter.get_name(),
    #     "online": True,
    #     "good": good,
    #     "nickname": nickname,
    # }


async def is_bot_online(bot_id: str) -> bool:
    status = await get_bot_status(bot_id)
    return bool(status["online"] and status.get("good"))


async def get_single_bot_status(code: str, all_fields: bool = False) -> BotStatus:
    """获取单个 bot 的状态，bot_id 不存在时抛出 HTTPException 404"""
    if code not in config.bots_list:
        raise HTTPException(status_code=404, detail=f"Bot {code} not found")
    return await get_bot_status(config.bots_list[code], all_fields=all_fields)


@cast(FastAPI, get_app()).get("/api/bots")
async def bots_status(_: Request, all_fields: bool = False) -> dict[str, BotStatus]:
    bots: dict[str, BotStatus] = {}
    for code, user_id in config.bots_list.items():
        bots[code] = await get_bot_status(user_id, all_fields=all_fields)
    return bots


@cast(FastAPI, get_app()).get("/api/bots/{bot_id}")
async def bot_status(bot_id: str, _: Request, all_fields: bool = False) -> BotStatus:
    return await get_single_bot_status(bot_id, all_fields=all_fields)


def assign_session(session_id: str, bot_id: str) -> None:
    sessions[session_id] = bot_id, time.time()
    logger.info(f"已将会话 {session_id} 分配给 {bot_id}")


def _is_self_bot_message(user_id: str) -> bool:
    """检查消息发送者是否属于 Moonlark 自身的 bot（包括 QQ 官方 bot）"""
    # 检查是否为同一个 NoneBot 实例下的其他 bot
    if user_id in get_bots():
        return True
    # 检查 QQ 官方 bot 的 app_id 映射（app_id 可能不在 get_bots() 中）
    if user_id in config.bots_appid_map:
        return True
    # 反向查找：user_id 是否在 appid_map 的 value 中（对应 bot 的 QQ 号）
    if user_id in config.bots_appid_map.values():
        return True
    return False


async def _lookup_bind_by_ob11_group(session_id: str) -> Optional[GroupBind]:
    """通过 OB11 的 session_id 查找 GroupBind"""
    from sqlalchemy import select
    # OB11 session_id 格式: onebot_v11_{qq_group_number}
    try:
        parts = session_id.rsplit("_", 1)
        if len(parts) == 2 and parts[0].startswith("onebot"):
            group_qq = parts[1]
            async with get_session() as db_session:
                result = await db_session.execute(
                    select(GroupBind).where(GroupBind.group_qq_number == group_qq)
                )
                return result.scalar_one_or_none()
    except Exception:
        pass
    return None


async def _lookup_bind_by_qqbot_group(session_id: str) -> Optional[GroupBind]:
    """通过 QQBot 的 session_id 查找 GroupBind"""
    from sqlalchemy import select
    try:
        # QQBot session_id 格式: qq_{group_openid}
        if session_id.startswith("qq_"):
            group_oid = session_id[3:]
            async with get_session() as db_session:
                result = await db_session.execute(
                    select(GroupBind).where(GroupBind.group_openid == group_oid)
                )
                return result.scalar_one_or_none()
    except Exception:
        pass
    return None


async def _get_bound_group(session_id: str) -> Optional[GroupBind]:
    """获取已绑定的群记录，用于判断是否为共享群"""
    bind = await _lookup_bind_by_ob11_group(session_id)
    if bind is not None:
        return bind
    return await _lookup_bind_by_qqbot_group(session_id)


def _is_qqbot_at_mentioned_in_ob11(event: Event) -> bool:
    """在 OB11 事件中检查 QQ 官方 bot 是否被 @
    
    通过 bots_appid_map 的值（QQ 号）和 bots_list 的值来匹配 @ 目标。
    """
    # 获取所有已知的 QQ bot 的 QQ 号
    known_qqbot_qq_numbers: set[str] = set(config.bots_appid_map.values())
    # 也加入 bots_list 中的值（某些 bot 可能没在 appid_map 中）
    known_qqbot_qq_numbers.update(config.bots_list.values())

    try:
        message = event.get_message()
        for segment in message:
            if segment.type == "at":
                # OB11 V11 的 at segment: data.qq 是 QQ 号
                at_qq = str(segment.data.get("qq", ""))
                if at_qq in known_qqbot_qq_numbers:
                    return True
                # 也检查 user_id 字段（某些适配器版本可能不同）
                at_user_id = str(segment.data.get("user_id", ""))
                if at_user_id in known_qqbot_qq_numbers:
                    return True
    except Exception:
        pass
    return False


def _should_bot_handle_in_shared_group(
    bot: Bot, event: Event, bind: GroupBind
) -> bool:
    """
    在同时含有 OB11 和 QQBot 的群聊中，判断当前 bot 是否应该处理此消息。
    
    规则：
    - 如果 @ 了 QQ bot → QQBot 处理
    - 否则 → OB11 优先处理
    """
    if isinstance(bot, QQBot):
        # QQ bot: 只在被 @ 时处理
        return bool(event.is_tome())
    elif isinstance(bot, V11Bot):
        # OB11 bot: 只在 QQ bot 未被 @ 时处理
        # 如果 QQ bot 被 @，OB11 不处理
        if _is_qqbot_at_mentioned_in_ob11(event):
            return False
        return True
    else:
        return True  # 其他类型的 bot 照常处理


from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.adapters import Message


class ToMeProcessor:

    def __init__(self, bot: Bot, event: Event, session_id: str) -> None:
        self.bot = bot
        self.event = event
        self.session_id = session_id
        self.to_me = False

    def process_to_me_event(self) -> None:
        if self.event.is_tome():
            return
        if (msg := self.get_event_message()) is not None:
            self.process_message_event(msg)
        elif isinstance(self.event, PokeNotifyEvent):
            self.process_poke()
        if self.to_me:
            self.event.is_tome = lambda _: True  # type: ignore

    def get_event_message(self) -> Optional[Message]:
        try:
            return self.event.get_message()
        except ValueError:
            return None

    def process_message_event(self, message: Message) -> None:
        for segment in message:
            if segment.type == "at":
                user_id = str(segment.get("user_id"))
                # 检查 bots_list 的 key（对应 bot 的 code）和 bots_appid_map 的 key（app_id）
                if user_id in config.bots_list.keys() or user_id in config.bots_appid_map.keys():
                    self.to_me = True
                    segment["user_id"] = self.bot.self_id

    def process_poke(self) -> None:
        event = cast(PokeNotifyEvent, self.event)
        target_id = str(event.target_id)
        if target_id in config.bots_list.keys() or target_id in config.bots_appid_map.keys():
            event.target_id = int(self.bot.self_id)
            self.to_me = True


@event_preprocessor
async def _(bot: Bot, event: Event, session_id: str = get_group_id()) -> None:
    try:
        user_id = event.get_user_id()
    except ValueError:
        user_id = None

    if user_id is not None:
        # 忽略来自自身 bot 的消息（包括 QQ 官方 bot 通过 appid_map 识别）
        if _is_self_bot_message(user_id):
            raise IgnoredException("忽略自身消息")

        # 检查是否为私聊消息
        try:
            is_private = event.get_session_id() == user_id
        except ValueError:
            is_private = False

        if is_private:
            # 检查用户是否关闭了该 bot 的私聊
            async with get_session() as session:
                settings = await session.get(UserBotPrivateChatSettings, {"user_id": user_id, "bot_id": bot.self_id})
                # 如果设置存在且私聊已关闭，检查是否为 .pm on 命令
                if settings is not None and not settings.private_chat_enabled:
                    plaintext = event.get_plaintext().strip()
                    if plaintext != ".pm on":
                        raise IgnoredException("用户已关闭该 bot 的私聊")

    # 绑定验证码检测（优先于路由，确保绑定消息被正确处理）
    # 仅在非私聊中检测
    if not (user_id is not None and event.get_session_id() == user_id):
        if await try_process_bind_code(bot, event, session_id):
            raise IgnoredException("绑定验证码已处理")

    # 在同时含有 OB11 和 QQBot 的群聊中使用优先级路由
    bind = await _get_bound_group(session_id)
    if bind is not None and bind.group_qq_number and bind.group_openid:
        # 此群同时有 OB11 和 QQBot，使用优先级路由
        if not _should_bot_handle_in_shared_group(bot, event, bind):
            raise IgnoredException(f"此消息由其他 bot 优先处理 (session={session_id})")
        # 如果此 bot 应该处理，分配 session
        assign_session(session_id, bot.self_id)
    else:
        # 普通群聊：原有逻辑
        # ToMe 处理
        if user_id is not None:
            ToMeProcessor(bot, event, session_id).process_to_me_event()

        if session_id in sessions and sessions[session_id][0] != bot.self_id:
            raise IgnoredException(f"此群组已分配给帐号 {session_id}")
        assign_session(session_id, bot.self_id)


@scheduler.scheduled_job("cron", minute="*", id="remove_expired_email")
async def _() -> None:
    expired_sessions = []
    for key, value in sessions.items():
        if time.time() - value[1] >= config.bots_session_remain or not await is_bot_online(value[0]):
            expired_sessions.append(key)
            logger.debug(f"将回收过期或不可用会话: {key} ({value})")
    for key in expired_sessions:
        sessions.pop(key)


async def get_group_bot(group_id: str) -> Optional[Bot]:
    """
    通过群 ID 获取一个 Bot 实例

    :param group_id: 群号
    :type group_id: str
    :return: Bot 实例
    :rtype: Bot | None
    """
    # 优先检查 session 中分配过的 bot
    if sessions.get(group_id) in (bots := get_bots()):
        return bots[sessions[group_id][0]]

    # 尝试遍历所有 bot 查找
    adapter_group_id = group_id.split("_", 1)[-1]
    for bot_id, bot in bots.items():
        if isinstance(bot, V11Bot):
            try:
                if adapter_group_id in [str(gid["group_id"]) for gid in await bot.get_group_list()]:
                    assign_session(group_id, bot_id)
                    return bot
            except Exception:
                continue

    # 通过 GroupBind 查找：如果是 QQBot 的 group_openid，查找绑定的 OB11 bot
    try:
        bind = await _lookup_bind_by_qqbot_group(group_id)
        if bind is not None and bind.group_qq_number:
            ob11_group_id = f"onebot_v11_{bind.group_qq_number}"
            if ob11_group_id in sessions:
                return bots.get(sessions[ob11_group_id][0])
    except Exception:
        pass

    return None
