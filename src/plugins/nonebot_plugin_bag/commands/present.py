import time
from types import SimpleNamespace

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, Option, Target, UniMessage, get_target, on_alconna
from nonebot_plugin_items.base.gift import GiftItem
from nonebot_plugin_larkuser import get_nickname, get_user, patch_matcher
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.user import get_user_id, is_private_message

from ..__main__ import lang
from ..item import BagItem
from ..utils.item import get_bag_items, get_bag_item

present = on_alconna(Alconna("present", Args["index?", int], Option("--count|-c", Args["count", int, 1])))
patch_matcher(present)

_present_cooldown: dict[str, float] = {}
PROACTIVE_COOLDOWN_SECONDS = 1800


async def _list_gifts(user_id: str) -> None:
    items = await get_bag_items(user_id)
    gift_items = [(it.index, it.stack) for it in items if isinstance(it.stack.item, GiftItem)]

    lines = [await lang.text("present.list_title", user_id)]
    if not gift_items:
        lines.append(await lang.text("present.list_empty", user_id))
    else:
        for idx, stack in gift_items:
            name = await stack.getName()
            lines.append(await lang.text("present.list_item", user_id, idx, name, stack.count))

    await present.finish("\n".join(lines))


async def _trigger_gift_response(
    bot: Bot,
    event: Event,
    user_id: str,
    group_id: str,
    is_private: bool,
    gift_item: GiftItem,
    item_name: str,
) -> None:
    try:
        from nonebot_plugin_chat.core.session import (
            create_private_session,
            get_session_directly,
            get_group_session_forced,
        )

        nickname = await get_nickname(user_id, bot, event)
        mock_stack = SimpleNamespace(user_id=user_id, count=1)

        try:
            session = get_session_directly(group_id)
            gift_prompt = await gift_item.getGiftPrompt(mock_stack, nickname)
            await session.add_event(gift_prompt, trigger_mode="all")
            return
        except KeyError:
            pass

        if is_private:
            target = get_target(event, bot)
            session = await create_private_session(group_id, target, bot)
            gift_prompt = await gift_item.getGiftPrompt(mock_stack, nickname)
            await session.add_event(gift_prompt, trigger_mode="all")
            return

        await _send_proactive_gift(bot, user_id, nickname, item_name)

    except Exception as e:
        logger.warning(f"触发礼物回复失败: {e}")


async def _send_proactive_gift(bot: Bot, user_id: str, nickname: str, item_name: str) -> None:
    from nonebot_plugin_chat.models import PrivateChatSession
    from nonebot_plugin_chat.core.session import create_private_session
    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    async with get_session() as db_session:
        result = await db_session.execute(select(PrivateChatSession).where(PrivateChatSession.user_id == user_id))
        chat_session = result.scalar_one_or_none()

    if not chat_session or not chat_session.session_key:
        logger.warning(f"用户 {user_id} 无私聊会话记录，无法发送主动礼物消息")
        return

    now = time.time()
    last_time = _present_cooldown.get(user_id)
    in_cooldown = last_time is not None and (now - last_time) < PROACTIVE_COOLDOWN_SECONDS

    adapter_name = bot.adapter.get_name()
    target = Target.user(user_id, adapter=adapter_name)
    session = await create_private_session(chat_session.session_key, target, bot)

    gift_prompt = f"{nickname} 送给你 {item_name}"

    if in_cooldown:
        await session.add_event(gift_prompt, trigger_mode="none")
        logger.info(f"礼物主动私聊冷却中，仅推送事件: user={user_id}, gift={item_name}")
    else:
        await session.add_event(gift_prompt, trigger_mode="all")
        _present_cooldown[user_id] = now
        logger.info(f"礼物主动私聊触发回复: user={user_id}, gift={item_name}")


@present.assign("$main")
async def _list(user_id: str = get_user_id()) -> None:
    await _list_gifts(user_id)


@present.handle()
async def _(
    bot: Bot,
    event: Event,
    index: int,
    count: int = 1,
    user_id: str = get_user_id(),
    is_private: bool = is_private_message(),
    group_id: str = get_group_id(),
) -> None:
    if count <= 0:
        await lang.finish("present.invalid_count", user_id)

    try:
        item = await get_bag_item(user_id, index)
    except IndexError:
        await lang.finish("show.index_error", user_id)

    if not isinstance(item.stack.item, GiftItem):
        await item.unlock_item()
        await lang.finish("present.not_gift", user_id)

    if count > item.stack.count:
        await item.unlock_item()
        await lang.finish("present.not_enough", user_id, item.stack.count)

    gift_item: GiftItem = item.stack.item
    item_name = await item.stack.getName()

    fav_increase = gift_item.fav_value * count
    user = await get_user(user_id)
    await user.add_fav(fav_increase)

    item.stack.count -= count
    await item.on_delete()

    await _trigger_gift_response(bot, event, user_id, group_id, is_private, gift_item, item_name)

    await lang.finish("present.success", user_id, item_name, count, round(fav_increase, 6))
