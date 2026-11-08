import json
from datetime import datetime
from typing import Literal

import aiofiles
from nonebot import get_bots
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import C2CMessageCreateEvent, GroupMessageCreateEvent
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Match,
    MultiVar,
    Subcommand,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.superuser import is_superuser
from nonebot_plugin_localstore import get_data_file
from typing_extensions import TypedDict

from .announcement import build_markdown, load_announcement, mark_update_read
from .groups import (
    get_event_group_key,
    list_group_snapshots,
    record_group_message,
    sync_bound_groups,
    sync_ob11_groups,
)
from .message import (
    MAX_BUTTONS,
    BroadcastButton,
    build_broadcast_message,
    build_qq_broadcast_message,
    render_broadcast_image,
)
from .push import push_broadcast

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


async def get_available_groups() -> AvailableGroups:
    """列出所有可推送广播的群聊

    群列表以 ``BroadcastGroup`` 表为准——它在每次收到群消息时更新，是 Moonlark
    内部最可靠的群列表。OneBot V11 与 GroupBind 只用来补充实时可达性：

    - OneBot V11：同步 ``get_group_list`` 的结果，群号可直接发送；
    - QQ 官方：没有群列表接口，使用表里记录过的 ``group_openid``；
      同一物理群若已被 OB11 覆盖则跳过，避免重复推送。

    返回值的键是实际发送时使用的群标识（OB11 群号或 QQ group_openid）。
    """
    data = await get_plugin_data()
    disabled = set(data["disabled_groups"])

    await sync_bound_groups()
    ob11_groups = await sync_ob11_groups()
    snapshots = await list_group_snapshots()
    qq_bots = [bot for bot in get_bots().values() if isinstance(bot, QQBot)]

    groups: AvailableGroups = {}
    for snapshot in snapshots:
        identifiers = (snapshot.group_key, snapshot.group_qq_number, snapshot.group_openid)
        if any(identifier is not None and identifier in disabled for identifier in identifiers):
            continue
        if snapshot.group_qq_number and snapshot.group_qq_number in ob11_groups:
            groups[snapshot.group_qq_number] = list(ob11_groups[snapshot.group_qq_number])
        elif snapshot.group_openid and qq_bots:
            groups[snapshot.group_openid] = list(qq_bots)
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
    # 每次广播都会写一条 BroadcastRecord 与每个群一条 BroadcastPushEvent；
    # 未开启主动消息推送的 QQ 群会转为被动消息，等该群下一条消息后补发。
    succeed_group, pending_group = await push_broadcast(
        await get_available_groups(), broadcast, buttons, submitter=user_id
    )
    if pending_group:
        await lang.finish("bcsu.broadcast_sent_pending", user_id, succeed_group, pending_group)
    await lang.finish("bcsu.broadcast_sent", user_id, succeed_group)


@bc_cmd.handle()
async def handle_bc(
    event: Event,
    action: str,
    user_id: str = get_user_id(),
):
    """Handle user broadcast settings"""
    group_key = await get_event_group_key(event)

    # 无参数时展示群开关与最新更新公告；私聊中也能查看公告（保留原 /updates 的用法）
    if not action:
        data = await get_plugin_data()
        announcement = await load_announcement()
        if announcement is not None:
            content = build_markdown(announcement)
            header = await lang.text("bc.announcement", user_id)
            buttons = [BroadcastButton(label=button.label, text=button.text) for button in announcement.buttons]
            await mark_update_read(user_id)
        else:
            content = data["latest"]
            header = await lang.text("bc.latest", user_id)
            buttons = data["buttons"]
        if not content:
            await lang.finish("bcsu.no_content", user_id)
        status_text = ""
        if group_key is not None:
            state = group_key not in data["disabled_groups"]
            status_text = await lang.text("bc.state", user_id, state)
        if isinstance(event, (GroupMessageCreateEvent, C2CMessageCreateEvent)):
            # QQ 官方：最后一次广播/更新公告同样以 markdown 发送
            await bc_cmd.finish(build_qq_broadcast_message(f"{status_text}{header}\n\n{content}", buttons))
            return
        await bc_cmd.finish(UniMessage().text(text=f"{status_text}{header}").image(raw=await md_to_pic(content)))
        return

    if group_key is None:
        await lang.finish("bc.group_only", user_id)
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
    # 把群登记进群列表：以后即使 QQ 官方接口拿不到群列表，也能从这张表广播
    await record_group_message(group_id if group_id.isdigit() else None, None if group_id.isdigit() else group_id)
    data = await get_plugin_data()
    if group_id not in data["disabled_groups"] and not enabled:
        data["disabled_groups"].append(group_id)
    elif group_id in data["disabled_groups"] and enabled:
        data["disabled_groups"].remove(group_id)
    await save_plugin_data(data)
