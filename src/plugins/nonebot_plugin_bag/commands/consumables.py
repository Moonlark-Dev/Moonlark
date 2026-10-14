from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

from nonebot_plugin_items.base.consumable import ConsumableItem
from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkutils.user import get_user_id

from ..exceptions import ItemLockedError
from ..item import BagItem
from ..utils.item import get_bag_item, get_bag_items
from ..__main__ import lang

consumables = on_alconna(
    Alconna(
        "consumables",
        Subcommand("use", Args["index", int], Args["count", int, 1]),
    ),
)
patch_matcher(consumables)

# 单次最多消耗的数量
MAX_USE_COUNT = 10


async def get_consumable_items(user_id: str) -> list[BagItem]:
    """获取背包中的全部消耗品"""
    items = await get_bag_items(user_id)
    return [item for item in items if isinstance(item.stack.item, ConsumableItem)]


@consumables.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    """查看背包中的消耗品"""
    items = await get_consumable_items(user_id)
    if not items:
        await consumables.finish(await lang.text("consumables.list_empty", user_id))
    lines = [await lang.text("consumables.list_title", user_id)]
    for item in items:
        lines.append(
            await lang.text(
                "consumables.list_item",
                user_id,
                item.index,
                await item.stack.getName(),
                item.stack.count,
                await item.stack.getDescription(),
            )
        )
    lines.append(await lang.text("consumables.list_footer", user_id))
    await consumables.finish("\n".join(lines))


@consumables.assign("use")
async def _(index: int, count: int = 1, user_id: str = get_user_id()) -> None:
    """使用背包中的消耗品（每次消耗一个并应用效果）"""
    if count <= 0:
        await lang.finish("consumables.invalid_count", user_id)
    count = min(count, MAX_USE_COUNT)
    try:
        item = await get_bag_item(user_id, index)
    except IndexError:
        await lang.finish("show.index_error", user_id)
    except ItemLockedError:
        await lang.finish("exc.locked", user_id)
    if not isinstance(item.stack.item, ConsumableItem):
        await item.unlock_item()
        await lang.finish("consumables.not_consumable", user_id)
    if count > item.stack.count:
        count = item.stack.count

    results = []
    for _ in range(count):
        result = await item.stack.item.on_use(item.stack)
        if result:
            results.append(result)
        item.stack.count -= 1
        if item.stack.count <= 0:
            break
    await item.on_delete()
    if results:
        await consumables.finish("\n".join(results))
    await lang.finish("consumables.use_done", user_id)
