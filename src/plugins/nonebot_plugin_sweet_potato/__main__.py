from __future__ import annotations

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, At, Button, Match, Subcommand, UniMessage, on_alconna
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_larkutils.command import get_command_prefix
from nonebot_plugin_larkutils.user import is_private_message
from nonebot_plugin_ranking import generate_image

from .lang import lang
from .potatoes import get_active_potato
from .room import MAX_PLAYERS, MIN_PLAYERS, HotPotatoRoom, get_rank_data, get_room, rooms

sweet_potato = on_alconna(
    Alconna(
        "sweet-potato",
        Subcommand("info"),
        Subcommand("rank"),
        Subcommand("create"),
        Subcommand("join"),
        Subcommand("start"),
        Subcommand("restart"),
        Subcommand("quit"),
        Subcommand("pass", Args["target?", At | str]),
        Subcommand("hold"),
    ),
)


async def require_group(private: bool, user_id: str) -> None:
    if private:
        await lang.finish("error.only_group", user_id)


async def require_registered(user_id: str) -> None:
    if not (await get_user(user_id)).is_registered():
        await lang.finish("error.not_registered", user_id)


async def get_play_room(group_id: str, user_id: str) -> HotPotatoRoom:
    room = get_room(group_id)
    if room is None:
        await lang.finish("error.no_room", user_id)
    if room.get_player(user_id) is None:
        await lang.finish("error.not_in_room", user_id)
    return room


async def send_rules(bot: Bot, event: Event, user_id: str, private: bool) -> None:
    """发送规则介绍：QQ 官方使用 markdown + 操作按钮，其他适配器渲染为图片。

    私聊（QQ 官方 C2C）不附带键盘按钮，只发送 markdown 规则。
    """
    markdown = await lang.text("info.rules", user_id)
    if isinstance(bot, QQBot):
        message = UniMessage().style(markdown, "markdown")
        if not private:
            prefix = get_command_prefix()
            message = message.keyboard(
                Button("enter", await lang.text("button.create", user_id), text=f"{prefix}sweet-potato create"),
                Button("enter", await lang.text("button.join", user_id), text=f"{prefix}sweet-potato join"),
                row=2,
            )
        await message.send(target=event, bot=bot)
        return
    await UniMessage().image(raw=await md_to_pic(markdown)).send(target=event, bot=bot)


@sweet_potato.assign("$main")
async def help_handler(
    bot: Bot,
    event: Event,
    user_id: str = get_user_id(),
    private: bool = is_private_message(),
) -> None:
    await send_rules(bot, event, user_id, private)
    await sweet_potato.finish()


@sweet_potato.assign("info")
async def info_handler(
    bot: Bot,
    event: Event,
    user_id: str = get_user_id(),
    private: bool = is_private_message(),
) -> None:
    await send_rules(bot, event, user_id, private)
    await sweet_potato.finish()


@sweet_potato.assign("rank")
async def rank_handler(user_id: str = get_user_id()) -> None:
    data = await get_rank_data(user_id)
    if not data:
        await lang.finish("rank.no_data", user_id)
    image = await generate_image(data, user_id, await lang.text("rank.title", user_id))
    await sweet_potato.finish(UniMessage().image(raw=image, name="image.png"))


@sweet_potato.assign("create")
async def create_handler(
    bot: Bot,
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    await require_group(private, user_id)
    await require_registered(user_id)
    existing = get_room(group_id)
    if existing is not None:
        if existing.status == "playing":
            await lang.finish("error.game_running", user_id)
        if existing.status == "waiting":
            await lang.finish("error.room_exists", user_id)
        # 游戏结束后再次 create：自动解散旧房间
        existing.dissolve()
    user = await get_user(user_id)
    room = HotPotatoRoom(group_id, user_id, bot, event, await get_active_potato(user_id))
    rooms[group_id] = room
    room.add_player(user_id, event.get_user_id(), user.get_nickname())
    await room.send_room_card(event, user_id, await lang.text("room.created", user_id))
    await sweet_potato.finish()


@sweet_potato.assign("join")
async def join_handler(
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    await require_group(private, user_id)
    await require_registered(user_id)
    room = get_room(group_id)
    if room is None:
        await lang.finish("error.no_room", user_id)
    if room.status == "playing":
        await lang.finish("error.game_running", user_id)
    if room.get_player(user_id) is not None:
        await lang.finish("error.already_in_room", user_id)
    if room.is_full:
        await lang.finish("error.room_full", user_id, MAX_PLAYERS)
    user = await get_user(user_id)
    room.add_player(user_id, event.get_user_id(), user.get_nickname())
    room.touch_ended()
    await room.send_room_card(event, user_id, await lang.text("room.joined", user_id, user.get_nickname()))
    await sweet_potato.finish()


@sweet_potato.assign("start")
async def start_handler(
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    await require_group(private, user_id)
    room = await get_play_room(group_id, user_id)
    if room.status == "playing":
        await lang.finish("error.game_running", user_id)
    if room.status == "ended":
        await lang.finish("error.use_restart", user_id)
    if room.owner != user_id:
        await lang.finish("error.not_owner", user_id)
    if len(room.players) < MIN_PLAYERS:
        await lang.finish("error.need_more_players", user_id, MIN_PLAYERS)
    room.update_event(event)
    room.begin()
    await sweet_potato.finish()


@sweet_potato.assign("restart")
async def restart_handler(
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    await require_group(private, user_id)
    room = await get_play_room(group_id, user_id)
    if room.status == "playing":
        await lang.finish("error.game_running", user_id)
    if room.status != "ended":
        await lang.finish("error.not_ended", user_id)
    if len(room.players) < MIN_PLAYERS:
        await lang.finish("error.need_more_players", user_id, MIN_PLAYERS)
    room.update_event(event)
    room.begin()
    await sweet_potato.finish()


@sweet_potato.assign("quit")
async def quit_handler(
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    await require_group(private, user_id)
    room = await get_play_room(group_id, user_id)
    if room.status == "playing":
        await lang.finish("error.quit_in_game", user_id)
    player = room.get_player(user_id)
    if player is None:
        await lang.finish("error.not_in_room", user_id)
    room.update_event(event)
    if room.owner == user_id:
        # 房主退出视为解散房间
        room.dissolve()
        await room.send_lang("room.disbanded", event=event)
    else:
        room.remove_player(player)
        room.touch_ended()
        await room.send_lang("room.player_left", player.nickname, event=event)
        if not room.players:
            rooms.pop(group_id, None)
    await sweet_potato.finish()


@sweet_potato.assign("pass")
async def pass_handler(
    event: Event,
    target: Match[At | str],
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    await require_group(private, user_id)
    room = await get_play_room(group_id, user_id)
    if room.status != "playing":
        await lang.finish("error.not_playing", user_id)
    if room.holder is None or room.holder.user_id != user_id:
        holder_name = room.holder.nickname if room.holder is not None else ""
        await lang.finish("error.not_your_turn", user_id, holder_name)
    if not target.available:
        await lang.finish("error.invalid_target", user_id)
    resolved = room.resolve_target(target.result)
    if resolved is None:
        await lang.finish("error.invalid_target", user_id)
    room.update_event(event)
    room.submit_action("pass", resolved)
    await sweet_potato.finish()


@sweet_potato.assign("hold")
async def hold_handler(
    event: Event,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    private: bool = is_private_message(),
) -> None:
    await require_group(private, user_id)
    room = await get_play_room(group_id, user_id)
    if room.status != "playing":
        await lang.finish("error.not_playing", user_id)
    if room.holder is None or room.holder.user_id != user_id:
        holder_name = room.holder.nickname if room.holder is not None else ""
        await lang.finish("error.not_your_turn", user_id, holder_name)
    room.update_event(event)
    room.submit_action("hold")
    await sweet_potato.finish()
