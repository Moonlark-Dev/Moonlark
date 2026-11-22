"""与 ``nonebot_plugin_chat`` 的桥接：游戏期间屏蔽闲聊，结束时投递汤面与汤底。

屏蔽通过 ``nonebot_plugin_chat.utils.suppression`` 完成（Chat 在生成回复前检查），
事件通过 ``session.add_event(..., trigger_mode="none")`` 投递——只记录、绝不回复。
所有 import 都放在函数内部：Chat 插件不可用时海龟汤依然能玩，只是不投递事件。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from nonebot import logger

from .lang import lang

if TYPE_CHECKING:
    from nonebot.adapters import Bot, Event

    from .types import Puzzle

# 屏蔽登记用的 owner（同一会话可有多个 owner 同时屏蔽）
OWNER = "turtle_soup"


def suspend(session_id: str) -> None:
    """让 Chat 暂停回复该会话。"""
    try:
        from nonebot_plugin_chat.utils.suppression import suspend_chat
    except Exception:
        logger.debug("海龟汤：Chat 插件不可用，跳过屏蔽")
        return
    suspend_chat(session_id, OWNER, "海龟汤进行中")
    logger.debug(f"海龟汤：已屏蔽会话 {session_id} 的 Chat 回复")


def resume(session_id: str) -> None:
    """恢复 Chat 对该会话的回复。"""
    try:
        from nonebot_plugin_chat.utils.suppression import resume_chat
    except Exception:
        logger.debug("海龟汤：Chat 插件不可用，跳过恢复")
        return
    resume_chat(session_id, OWNER)
    logger.debug(f"海龟汤：已恢复会话 {session_id} 的 Chat 回复")


async def _chat_enabled(event: Event, session_id: str, user_id: str) -> bool:
    """该会话的 Chat 是否处于开启状态；无法判断时按开启处理。"""
    try:
        from nonebot_plugin_chat.utils.group import enabled_group, enabled_private_chat

        if await enabled_group(event, session_id):
            return True
        return await enabled_private_chat(event, user_id)
    except Exception:
        return True


async def publish_summary(
    session_id: str,
    bot: Bot,
    event: Event,
    puzzle: Puzzle,
    *,
    user_id: str,
    solved: bool,
) -> None:
    """把汤面与汤底作为一条 ``trigger_mode="none"`` 的事件投递给 Chat。

    事件只进入会话上下文（Moonlark 会"记得"这局游戏），不会触发任何回复。
    必须在 :func:`resume` 之前调用，避免游戏期间排队的消息在恢复时被一起回复。
    """
    try:
        from nonebot_plugin_chat.core.session import get_session_directly
        from nonebot_plugin_larkutils.gift_session import get_or_create_session
    except Exception:
        logger.debug("海龟汤：Chat 插件不可用，跳过事件投递")
        return

    key = "chat.event_solved" if solved else "chat.event_given_up"
    prompt = await lang.text(key, user_id, puzzle.puzzle_setting, puzzle.solution)

    try:
        session = get_session_directly(session_id)
    except KeyError:
        session = None
    if session is None:
        if not await _chat_enabled(event, session_id, user_id):
            logger.debug(f"海龟汤：会话 {session_id} 未开启 Chat，跳过事件投递")
            return
        session = await get_or_create_session(session_id, bot, event)
    if session is None:
        logger.debug(f"海龟汤：无法获取会话 {session_id}，跳过事件投递")
        return
    await session.add_event(prompt, trigger_mode="none")
    logger.debug(f"海龟汤：已向会话 {session_id} 投递汤面与汤底（trigger_mode=none）")


async def drain_session(session_id: str, wait_seconds: float = 3.0) -> None:
    """等待 Chat 把屏蔽期间排队的消息消费完（这些消息不会触发回复）。

    Chat 的回复任务在生成前会检查屏蔽，因此这里只需等队列被取空；超时则放弃，
    宁可让少量排队消息在恢复后进入判定，也不阻塞游戏结算。
    """
    try:
        from nonebot_plugin_chat.core.session import get_session_directly
    except Exception:
        return
    try:
        session = get_session_directly(session_id)
    except KeyError:
        return
    deadline = time.monotonic() + wait_seconds
    # Chat 的队列没有可等待的 Event，只能短轮询；最长只等 wait_seconds
    while session.message_queue and time.monotonic() < deadline:  # ruff: ignore[async-busy-wait]
        await asyncio.sleep(0.05)
