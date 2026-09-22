import asyncio
import json
import random
import traceback
from datetime import datetime
from typing import Literal, Optional

import aiofiles
from nonebot import get_bots
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Bot as V11Bot, GroupMessageEvent
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.log import logger
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Button,
    Match,
    MultiVar,
    Subcommand,
    Target,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_bots.models import GroupBind
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.superuser import is_superuser
from nonebot_plugin_localstore import get_data_file
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from typing_extensions import TypedDict

# Initialize language helper
lang = LangHelper()
data_file = get_data_file("nonebot_plugin_broadcast", "data.json")

# QQ 官方键盘最多支持 25 个按钮
MAX_BUTTONS = 25

# 长度达到该值的广播在其余平台会被渲染为图片
IMAGE_RENDER_THRESHOLD = 200


class BroadcastButton(TypedDict):
    """广播附带的 QQ 官方自定义按钮"""

    label: str
    text: str


class BroadcastDataCounter(TypedDict):
    update_at: list[int]
    sent_count: int


class BroadcastDataFile(TypedDict):
    counter: BroadcastDataCounter
    latest: str
    disabled_groups: list[str]
    buttons: list[BroadcastButton]


AvailableGroups = dict[str, list[Bot]]


async def get_plugin_data() -> BroadcastDataFile:
    if data_file.exists():
        async with aiofiles.open(data_file, encoding="utf-8") as f:
            data = json.loads(await f.read())
        # 兼容旧数据文件：历史版本没有 buttons 字段
        data.setdefault("buttons", [])
        return BroadcastDataFile(**data)
    dt = datetime.now()
    return BroadcastDataFile(
        counter=BroadcastDataCounter(update_at=[dt.year, dt.month], sent_count=0),
        latest="",
        disabled_groups=[],
        buttons=[],
    )


async def save_plugin_data(data: BroadcastDataFile) -> None:
    async with aiofiles.open(data_file, "w", encoding="utf-8") as file:
        await file.write(json.dumps(data, indent=4, ensure_ascii=False))


cached_broadcast_content = ""


# Define commands
def build_bcsu_alconna() -> Alconna:
    """构建 bcsu 命令

    独立成工厂函数，便于测试直接构造一份未被事件响应器改写的干净副本。

    注意 `MultiVar` 必须使用 `MultiVar(str)`（调用式）而不是 `MultiVar[str]`
    （下标式）：同一条命令中出现多个 MultiVar 时，下标式会让参数绑定到错误的
    名字上（例如 text 被塞进 content），导致解析失败。
    """
    return Alconna(
        "bcsu",
        Subcommand("submit"),
        Subcommand("clear"),
        Subcommand("preview"),
        Subcommand(
            "button",
            # action 必须显式给出：若把 action 声明为可选，`bcsu button clear` 中的
            # clear 会被顶层 clear 子命令抢走，导致广播内容被误清除
            Args["action", Literal["add", "remove", "clear", "list"]],
            Args["label?", str],
            Args["text?", MultiVar(str)],
        ),
        Args["content?", MultiVar(str)],
    )


bcsu_alc = build_bcsu_alconna()
bcsu_cmd = on_alconna(bcsu_alc, permission=is_superuser, block=True)

bc_cmd = on_alconna(Alconna("bc", Args["action?", Literal["on", "off", "enable", "disable", ""], ""]), block=False)


async def resolve_group_key(group_id: str) -> str:
    """把群标识归一化为广播开关使用的键

    OB11 群号保持原样；QQ 官方的 group_openid 若已与群号绑定则使用群号，
    这样同一个物理群在两种协议下的开关状态一致。
    """
    group_id = group_id.removeprefix("qq_")
    if group_id.isdigit():
        return group_id
    async with get_session() as session:
        bind = await session.scalar(select(GroupBind).where(GroupBind.group_openid == group_id))
    if bind is not None and bind.group_qq_number:
        return bind.group_qq_number
    return group_id


async def get_event_group_key(event: Event) -> Optional[str]:
    """获取事件所在群的广播开关键，非群聊事件返回 None"""
    if isinstance(event, GroupMessageEvent):
        return await resolve_group_key(str(event.group_id))
    if isinstance(event, GroupMessageCreateEvent):
        return await resolve_group_key(event.group_openid)
    return None


async def get_available_groups() -> AvailableGroups:
    """列出所有可推送广播的群聊

    - OneBot V11：通过 `get_group_list` 获取群号；
    - QQ 官方：官方接口没有群列表，改用已绑定的 `group_openid`；
      同一物理群若已被 OB11 覆盖则跳过，避免重复推送。

    返回值的键是实际发送时使用的群标识（OB11 群号或 QQ group_openid）。
    """
    groups: AvailableGroups = {}
    data = await get_plugin_data()
    disabled = set(data["disabled_groups"])
    bots = list(get_bots().values())

    ob11_group_ids: set[str] = set()
    for bot in bots:
        if not isinstance(bot, V11Bot):
            continue
        try:
            group_list = await bot.get_group_list()
        except Exception:
            logger.warning(f"获取 {bot.self_id} 的群列表失败：{traceback.format_exc()}")
            continue
        for group in group_list:
            group_id = str(group["group_id"])
            ob11_group_ids.add(group_id)
            if group_id in disabled:
                continue
            if bot not in groups.setdefault(group_id, []):
                groups[group_id].append(bot)

    qq_bots = [bot for bot in bots if isinstance(bot, QQBot)]
    if qq_bots:
        async with get_session() as session:
            binds = (await session.scalars(select(GroupBind).where(GroupBind.group_openid.is_not(None)))).all()
        for bind in binds:
            openid = bind.group_openid
            if not openid:
                continue
            if (bind.group_qq_number or openid) in disabled:
                continue
            if bind.group_qq_number and bind.group_qq_number in ob11_group_ids:
                # 同一物理群 OB11 已覆盖
                continue
            for bot in qq_bots:
                if bot not in groups.setdefault(openid, []):
                    groups[openid].append(bot)

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


def build_qq_broadcast_message(content: str, buttons: list[BroadcastButton]) -> UniMessage:
    """构建 QQ 官方广播消息：直接以 markdown 发送并附上自定义按钮"""
    message = UniMessage().style(content, "markdown")
    if buttons:
        message.keyboard(
            *[Button("enter", button["label"], text=button["text"]) for button in buttons[:MAX_BUTTONS]],
            row=5,
        )
    return message


async def build_broadcast_message(
    bot: Bot, content: str, buttons: list[BroadcastButton], image: Optional[bytes] = None
) -> UniMessage:
    """按适配器构建广播消息

    QQ 官方机器人直接发送 markdown（不渲染图片），其余平台保持原有行为：
    内容较长时渲染为图片，否则发送纯文本。
    """
    if isinstance(bot, QQBot):
        return build_qq_broadcast_message(content, buttons)
    if len(content) >= IMAGE_RENDER_THRESHOLD:
        return UniMessage().image(raw=image if image is not None else await md_to_pic(content))
    return UniMessage().text(text=content)


async def render_broadcast_image(content: str) -> Optional[bytes]:
    """仅在需要图片渲染时生成一次图片"""
    if len(content) < IMAGE_RENDER_THRESHOLD:
        return None
    return await md_to_pic(content)


@bcsu_cmd.assign("preview")
async def preview_broadcast(bot: Bot, user_id: str = get_user_id()):
    """Preview broadcast content"""
    if not cached_broadcast_content:
        await lang.finish("bcsu.no_content", user_id)
    buttons = (await get_plugin_data())["buttons"]
    image = None if isinstance(bot, QQBot) else await render_broadcast_image(cached_broadcast_content)
    message = await build_broadcast_message(bot, cached_broadcast_content, buttons, image)
    await message.send()
    await bcsu_cmd.finish()


async def set_latest_broadcast_content(content: str) -> None:
    data = await get_plugin_data()
    data["latest"] = content
    await save_plugin_data(data)


@bcsu_cmd.assign("button")
async def handle_button(
    action: Match[str],
    label: Match[str],
    text: Match[list[str]],
    user_id: str = get_user_id(),
):
    """管理广播附带的 QQ 官方自定义按钮"""
    action_value = action.result if action.available else "list"
    data = await get_plugin_data()

    if action_value == "list":
        if not data["buttons"]:
            await lang.finish("bcsu.button_empty", user_id)
        lines = [await lang.text("bcsu.button_list", user_id)]
        for button in data["buttons"]:
            lines.append(await lang.text("bcsu.button_item", user_id, button["label"], button["text"]))
        await lang.finish("bcsu.button_list_footer", user_id, "\n".join(lines))

    if action_value == "clear":
        count = len(data["buttons"])
        data["buttons"] = []
        await save_plugin_data(data)
        await lang.finish("bcsu.button_cleared", user_id, count)

    if not label.available:
        await lang.finish("bcsu.button_usage", user_id)

    if action_value == "remove":
        remain = [button for button in data["buttons"] if button["label"] != label.result]
        if len(remain) == len(data["buttons"]):
            await lang.finish("bcsu.button_not_found", user_id, label.result)
        data["buttons"] = remain
        await save_plugin_data(data)
        await lang.finish("bcsu.button_removed", user_id, label.result)

    if action_value == "add":
        command = " ".join(text.result).strip() if text.available else ""
        if not command:
            await lang.finish("bcsu.button_usage", user_id)
        if len(data["buttons"]) >= MAX_BUTTONS:
            await lang.finish("bcsu.button_full", user_id, MAX_BUTTONS)
        data["buttons"] = [button for button in data["buttons"] if button["label"] != label.result]
        data["buttons"].append(BroadcastButton(label=label.result, text=command))
        await save_plugin_data(data)
        await lang.finish("bcsu.button_added", user_id, label.result, command)

    await lang.finish("bcsu.button_usage", user_id)


@bcsu_cmd.assign("submit")
async def submit_broadcast(user_id: str = get_user_id()):
    """Submit broadcast to all enabled groups"""
    broadcast = cached_broadcast_content
    if not broadcast:
        await lang.send("bcsu.no_content", user_id)
        return
    buttons = (await get_plugin_data())["buttons"]
    await set_latest_broadcast_content(broadcast)
    succeed_group = 0
    # 图片只渲染一次，供所有非 QQ 平台复用
    image: Optional[bytes] = None
    for group_id, bots in (await get_available_groups()).items():
        for bot in bots:
            try:
                if image is None and not isinstance(bot, QQBot):
                    image = await render_broadcast_image(broadcast)
                message = await build_broadcast_message(bot, broadcast, buttons, image)
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
    event: Event,
    action: str,
    user_id: str = get_user_id(),
):
    """Handle user broadcast settings"""
    # Check if this is a group message
    group_key = await get_event_group_key(event)
    if group_key is None:
        await lang.finish("bc.group_only", user_id)

    # If no action, show current status
    if not action:
        data = await get_plugin_data()
        state = group_key not in data["disabled_groups"]
        status_text = await lang.text("bc.state", user_id, state)
        if data["latest"]:
            if isinstance(event, GroupMessageCreateEvent):
                # QQ 官方：最后一次广播同样以 markdown 发送
                await bc_cmd.finish(UniMessage().style(f"{status_text}\n\n{data['latest']}", "markdown"))
            msg = UniMessage().text(text=status_text).image(raw=await md_to_pic(data["latest"]))
        else:
            msg = UniMessage().text(text=status_text).text(text=await lang.text("bcsu.no_content", user_id))
        await bc_cmd.finish(msg)
    # Handle enable/disable
    if action.lower() in ["on", "enable"]:
        await set_group_broadcast_setting(group_key, True)
        await lang.finish("bc.enabled", user_id)
    elif action.lower() in ["off", "disable"]:
        await set_group_broadcast_setting(group_key, False)
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
    await save_plugin_data(data)
