import asyncio
import json
import random
import traceback

import aiofiles
from nonebot_plugin_alconna import on_alconna, Alconna, Args, MultiVar, Subcommand, UniMessage
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils.superuser import is_superuser
from nonebot.adapters.onebot.v11 import Bot as V11Bot, GroupMessageEvent
from nonebot.adapters import Event
from nonebot import get_bots
from nonebot.log import logger
from nonebot_plugin_htmlrender import md_to_pic
from datetime import datetime
from nonebot_plugin_localstore import get_data_file
from typing import List, Literal, TypedDict

# Initialize language helper
lang = LangHelper()
data_file = get_data_file("nonebot_plugin_broadcast", "data.json")


class BroadcastDataCounter(TypedDict):
    update_at: list[int]
    sent_count: int


class BroadcastDataFile(TypedDict):
    counter: BroadcastDataCounter
    latest: str
    disabled_groups: list[str]


AvailableGroups = dict[str, list[V11Bot]]


async def get_plugin_data() -> BroadcastDataFile:
    if data_file.exists():
        async with aiofiles.open(data_file, encoding="utf-8") as f:
            return BroadcastDataFile(**json.loads(await f.read()))
    dt = datetime.now()
    return BroadcastDataFile(
        counter=BroadcastDataCounter(update_at=[dt.year, dt.month], sent_count=0), latest="", disabled_groups=[]
    )


cached_broadcast_content = ""

# Define commands
bcsu_cmd = on_alconna(
    Alconna(
        "bcsu",
        Subcommand("submit"),
        Subcommand("clear"),
        Subcommand("preview"),
        Args["content?", MultiVar(str)],
    ),
    permission=is_superuser,
    block=True,
)

bc_cmd = on_alconna(Alconna("bc", Args["action?", Literal["on", "off", "enable", "disable", ""], ""]), block=False)


async def get_available_groups() -> AvailableGroups:
    groups: AvailableGroups = {}
    data = await get_plugin_data()
    for bot in get_bots().values():
        if not isinstance(bot, V11Bot):
            continue
        for group in await bot.get_group_list():
            group_id = str(group["group_id"])
            if group_id not in data["disabled_groups"]:
                if group_id not in groups:
                    groups[group_id] = [bot]
                else:
                    groups[group_id].append(bot)
    return groups


@bcsu_cmd.assign("content")
async def handle_bcsu(
    event: Event,
    user_id: str = get_user_id(),
):
    """Handle broadcast superuser commands"""
    content = event.get_plaintext()[6:].strip()
    await set_broadcast_content(user_id, content)


@bcsu_cmd.assign("$main")
async def show_broadcast_menu(user_id: str = get_user_id()):
    """Show broadcast menu with stats"""
    # Get broadcast stats
    current_month = datetime.now().month
    current_year = datetime.now().year
    data = await get_plugin_data()
    if data["counter"]["update_at"] != [current_year, current_month]:
        data["counter"]["sent_count"] = 0
    sent_count = data["counter"]["sent_count"]
    # Count enabled groups
    enabled_count = len((await get_available_groups()).keys())
    await lang.finish("bcsu.menu", user_id, sent_count, enabled_count)


async def set_broadcast_content(user_id: str, content: str):
    """Set broadcast content"""
    global cached_broadcast_content
    cached_broadcast_content = content
    await lang.finish("bcsu.content_set", user_id)


@bcsu_cmd.assign("clear")
async def clear_broadcast(user_id: str = get_user_id()):
    """Clear broadcast content"""
    global cached_broadcast_content
    cached_broadcast_content = ""
    await lang.finish("bcsu.cleared", user_id)


@bcsu_cmd.assign("preview")
async def preview_broadcast(user_id: str = get_user_id()):
    """Preview broadcast content"""
    if cached_broadcast_content:
        broadcast = cached_broadcast_content
        if len(broadcast) >= 200:
            message = UniMessage().image(raw=await md_to_pic(broadcast))
        else:
            message = UniMessage().text(text=broadcast)
        await message.send()
    else:
        await lang.finish("bcsu.no_content", user_id)


async def set_latest_broadcast_content(content: str) -> None:
    data = await get_plugin_data()
    data["latest"] = content
    async with aiofiles.open(data_file, "w", encoding="utf-8") as file:
        await file.write(json.dumps(data, indent=4, ensure_ascii=False))


from nonebot_plugin_alconna import Target


@bcsu_cmd.assign("submit")
async def submit_broadcast(user_id: str = get_user_id()):
    """Submit broadcast to all enabled groups"""
    broadcast = cached_broadcast_content
    if not broadcast:
        await lang.send("bcsu.no_content", user_id)
        return
    if len(broadcast) >= 200:
        message = UniMessage().image(raw=await md_to_pic(broadcast))
    else:
        message = UniMessage().text(text=broadcast)
    await set_latest_broadcast_content(broadcast)
    succeed_group = 0
    for group_id, bots in (await get_available_groups()).items():
        for bot in bots:
            try:
                await message.send(
                    target=Target(group_id, self_id=bot.self_id, adapter=bot.adapter.get_name()), bot=bot
                )
                succeed_group += 1
                break
            except Exception as _:
                logger.warning(f"使用 {bot.self_id} 在 {group_id} 推送失败：{traceback.format_exc()}")
            await asyncio.sleep(random.randint(1, 7))
    await lang.finish("bcsu.broadcast_sent", user_id, succeed_group)


@bc_cmd.handle()
async def handle_bc(
    event: GroupMessageEvent,
    action: str,
    user_id: str = get_user_id(),
):
    """Handle user broadcast settings"""
    # Check if this is a group message
    if not isinstance(event, GroupMessageEvent):
        await lang.send("bc.group_only", user_id)
        return

    group_id = str(event.group_id)

    # If no action, show current status
    if not action:
        data = await get_plugin_data()
        state = group_id not in data["disabled_groups"]
        msg = UniMessage().text(text=await lang.text("bc.state", user_id, state))
        if data["latest"]:
            msg = msg.image(raw=await md_to_pic(data["latest"]))
        else:
            msg = msg.text(text=await lang.text("bcsu.no_content", user_id))
        await bc_cmd.finish(msg)
    # Handle enable/disable
    if action.lower() in ["on", "enable"]:
        await set_group_broadcast_setting(group_id, True)
        await lang.finish("bc.enabled", user_id)
    elif action.lower() in ["off", "disable"]:
        await set_group_broadcast_setting(group_id, False)
        await lang.finish("bc.disabled", user_id)
    else:
        await lang.finish("bc.invalid_action", user_id)


async def set_group_broadcast_setting(group_id: str, enabled: bool):
    """Set group broadcast setting"""
    data = await get_plugin_data()
    if group_id not in data["disabled_groups"] and not enabled:
        data["disabled_groups"].append(group_id)
    elif group_id in data["disabled_groups"] and enabled:
        data["disabled_groups"].remove(group_id)
    async with aiofiles.open(data_file, "w", encoding="utf-8") as file:
        await file.write(json.dumps(data, indent=4, ensure_ascii=False))
