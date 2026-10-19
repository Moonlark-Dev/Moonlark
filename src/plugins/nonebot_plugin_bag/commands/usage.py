from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_larkutils.command import get_command_prefix

from ..item import BagItem
from ..utils.item import get_bag_item, get_bag_items
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import bag, lang

# QQ 官方机器人键盘的按钮上限（保守值，避免消息被拒绝）
MAX_BUTTONS = 8


async def collect_usage_items(user_id: str, index: int | None = None) -> list[tuple[BagItem, str]]:
    """收集需要展示使用指令的物品：(物品, 使用说明文本)"""
    try:
        items = [await get_bag_item(user_id, index, True)] if index is not None else await get_bag_items(user_id)
    except IndexError:
        await lang.finish("show.index_error", user_id)
    pairs = []
    for item in items:
        usage = await item.stack.item.getUsageDescription(item.stack)
        if item.stack.item.usage_command and usage:
            pairs.append((item, usage))
    return pairs


@bag.assign("usage")
async def _(bot: Bot, event: Event, index: int | None = None, user_id: str = get_user_id()) -> None:
    """查看背包物品的使用指令；提供序号时只展示该物品。

    QQ 官方机器人会附带按钮：点击后把对应的使用指令填进输入框。
    """
    usage_items = await collect_usage_items(user_id, index)
    if not usage_items:
        if index is not None:
            await lang.finish("usage.none_single", user_id)
        await lang.finish("usage.none", user_id)

    # QQ 官方机器人发送 markdown：用法用围栏代码块包裹，避免 <@目标> 等尖括号被
    # 当成 HTML 标签吞掉，也方便用户直接复制；其余平台保持纯文本。
    is_qq = isinstance(bot, QQBot)
    item_key = "usage.item_md" if is_qq else "usage.item"
    lines = [await lang.text("usage.title", user_id)] if index is None else []
    for item, usage in usage_items:
        lines.append(
            await lang.text(
                item_key,
                user_id,
                item.index,
                await item.stack.getName(),
                item.stack.count,
                usage,
            )
        )

    if is_qq:
        buttons = [
            Button(
                "enter",
                f"{await item.stack.getName()} x{item.stack.count}",
                text=f"{get_command_prefix()}{item.stack.item.usage_command}",
            )
            for item, _usage in usage_items[:MAX_BUTTONS]
        ]
        if buttons:
            message = UniMessage().style("\n".join(lines), "markdown").keyboard(*buttons)
            await message.send(target=event, bot=bot)
            await bag.finish()
    await bag.finish("\n".join(lines))
