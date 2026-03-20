from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand
from nonebot_plugin_chat.core.session import post_group_event
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.jrrp import get_luck_value, reroll_luck_value, get_luck_value_with_reroll_count
from nonebot_plugin_schedule.utils import complete_schedule
from .utils import get_luck_message, get_luck_type
from nonebot_plugin_larkutils import get_user_id
from nonebot.adapters import Bot, Event
from .lang import lang

alc = Alconna("jrrp",
    Subcommand("--rank|-r|r"),
    Subcommand("--rank-r|-rr|rr"),
    Subcommand("reroll")
)
jrrp = on_alconna(alc)


async def process_jrrp_command(group_id: str, user_id: str, bot: Bot, event: Event) -> None:
    await post_group_event(
        group_id,
        await lang.text("chat_event", user_id, await get_nickname(user_id, bot, event), await get_luck_value(user_id)),
        "probability",
    )
    await jrrp.finish(await get_luck_message(user_id), at_sender=True)

@jrrp.assign("$main")
async def _(bot: Bot, event: Event, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    await complete_schedule(user_id, "jrrp")
    await process_jrrp_command(group_id, user_id, bot, event)


@jrrp.assign("reroll")
async def _(bot: Bot, event: Event, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    """重新计算今日人品值"""
    from .config import config
    
    MAX_REROLL_COUNT = config.jrrp_reroll_max_count
    
    # 获取用户数据
    user = await get_user(user_id)
    
    # 获取当前人品值和已重算次数
    current_luck, reroll_count = await get_luck_value_with_reroll_count(user_id)
    
    # 检查是否已达到重算上限
    if reroll_count >= MAX_REROLL_COUNT:
        await lang.finish("reroll.max_reached", user_id, MAX_REROLL_COUNT, at_sender=True)
        return
    
    # 计算本次重算所需费用
    cost = config.jrrp_reroll_base_cost * (reroll_count + 1)
    
    # 检查用户是否有足够的 vimcoin
    if not await user.has_vimcoin(cost):
        await lang.finish("reroll.insufficient_vimcoin", user_id, cost, round(user.get_vimcoin(), 2), at_sender=True)
        return
    
    # 扣除 vimcoin
    await user.use_vimcoin(cost)
    
    # 重新计算人品值
    result = await reroll_luck_value(user_id, MAX_REROLL_COUNT)
    if result is None:
        await lang.finish("reroll.max_reached", user_id, MAX_REROLL_COUNT, at_sender=True)
        return
    
    new_luck, new_reroll_count = result
    luck_type = get_luck_type(new_luck)
    
    # 发送结果
    await lang.send(
        "reroll.success",
        user_id,
        new_reroll_count,
        MAX_REROLL_COUNT,
        cost,
        at_sender=True
    )

    await process_jrrp_command(group_id, user_id, bot, event)
