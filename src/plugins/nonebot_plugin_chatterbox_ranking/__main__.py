from datetime import date, timedelta
from typing import Literal
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils.file import FileType
from sqlalchemy import func, select
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot import on_message
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import (
    on_alconna,
    Alconna,
    Arparma,
    Args,
    At,
    Button,
    Option,
    Subcommand,
    UniMessage,
)
from nonebot_plugin_larkutils import get_user_id, get_group_id, open_file
from nonebot_plugin_larkutils.command import get_command_prefix
from .image import render_bar
from .lang import lang
from .models import GroupChatterbox, GroupChatterboxWithNickname

SpanType = Literal["total", "7d", "1d"]

# 时间段按钮的文案 key，顺序即键盘上的排列顺序
SPAN_BUTTON_KEYS: dict[SpanType, str] = {
    "total": "button.span_total",
    "7d": "button.span_7d",
    "1d": "button.span_1d",
}

chatterbox = on_alconna(
    Alconna(
        "chatterbox",
        Subcommand("--enable|-e"),
        Subcommand("--disable|-d"),
        Option("--global|-g"),
        Args["span?", Literal["total", "7d", "1d"]]["user_id_arg?", Literal["me"] | At],
    ),
    aliases={"ct"},
)

recorder = on_message(priority=3, block=False)


def build_rank_command(span: SpanType, global_flag: bool = False, user_id_arg: Literal["me"] | None = None) -> str:
    """拼出跳转到指定排行榜的指令文本。

    QQ 官方的 enter 按钮会把这段文本原样发回聊天，因此必须是完整可解析的指令。
    """
    argv = [f"{get_command_prefix()}chatterbox", span]
    if user_id_arg is not None:
        argv.append(user_id_arg)
    if global_flag:
        argv.append("--global")
    return " ".join(argv)


async def build_rank_buttons(user_id: str, span: SpanType, global_flag: bool) -> list[Button]:
    """构建 QQ 官方排行榜的跳转按钮。

    依次是三个时间段的榜单、另一个统计范围（本群/全局）以及本人的排名，
    让用户不必手打指令即可切换榜单。
    """
    buttons = [
        Button("enter", await lang.text(lang_key, user_id), text=build_rank_command(item, global_flag))
        for item, lang_key in SPAN_BUTTON_KEYS.items()
    ]
    buttons.extend(
        [
            Button(
                "enter",
                await lang.text("button.scope_group" if global_flag else "button.scope_global", user_id),
                text=build_rank_command(span, not global_flag),
            ),
            Button("enter", await lang.text("button.me", user_id), text=build_rank_command(span, global_flag, "me")),
        ],
    )
    return buttons


async def send_rank_with_buttons(
    bot: Bot,
    event: Event,
    user_id: str,
    span: SpanType,
    global_flag: bool,
    image: bytes,
) -> None:
    """QQ 官方：图片消息（msg_type 7）无法携带按钮，因此在排行榜图片之后再发一条带按钮的 markdown。"""
    await UniMessage().image(raw=image).send(target=event, bot=bot)
    await (
        UniMessage()
        .style(await lang.text("button.tip", user_id), "markdown")
        # row=3：三个时间段按钮占一行，统计范围与本人排名占第二行
        .keyboard(*await build_rank_buttons(user_id, span, global_flag), row=3)
        .send(target=event, bot=bot)
    )


def get_start_date(span: SpanType) -> date | None:
    if span == "7d":
        return date.today() - timedelta(days=6)
    elif span == "1d":
        return date.today()
    return None


def build_rank_statement(span: SpanType, group_id: str | None):
    total = func.sum(GroupChatterbox.message_count).label("total_count")
    stmt = select(GroupChatterbox.user_id, total)
    if group_id is not None:
        stmt = stmt.where(GroupChatterbox.group_id == group_id)
    start_date = get_start_date(span)
    if start_date is not None:
        stmt = stmt.where(GroupChatterbox.record_date >= start_date)
    return stmt.group_by(GroupChatterbox.user_id).order_by(total.desc())


async def get_scope_span_text(user_id: str, span: SpanType, global_flag: bool) -> tuple[str, str]:
    scope_text = await lang.text("bar.scope_global" if global_flag else "bar.scope_group", user_id)
    span_text = await lang.text(f"bar.span_{span}", user_id)
    return scope_text, span_text


@chatterbox.assign("enable")
async def _(bot: Bot, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if isinstance(bot, Bot_QQ):
        await lang.finish("switch.unsupported", user_id)
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id not in f.data:
            f.data.append(group_id)
    await lang.finish("switch.enable", user_id)


@chatterbox.assign("disable")
async def _(user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
            f.data.pop(f.data.index(group_id))
    await lang.finish("switch.disable", user_id)


@chatterbox.assign("user_id_arg")
async def _(
    session: async_scoped_session,
    result: Arparma,
    span: SpanType = "total",
    user_id_arg: Literal["me"] | At = "me",
    sender_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
            await lang.finish("disabled", sender_id)
    if user_id_arg == "me":
        user_id = sender_id
    else:
        user_id = user_id_arg.target
    global_flag = result.find("global")
    scope_text, span_text = await get_scope_span_text(sender_id, span, global_flag)
    index = 1
    for row in await session.execute(build_rank_statement(span, None if global_flag else group_id)):
        if row.user_id == user_id:
            await lang.finish("find.result", user_id, scope_text, span_text, user_id, index, row.total_count)
        index += 1
    await lang.finish("find.not_found", user_id)


@chatterbox.handle()
async def _(
    bot: Bot,
    event: Event,
    session: async_scoped_session,
    result: Arparma,
    span: SpanType = "total",
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
            await lang.finish("disabled", user_id)
    global_flag = bool(result.find("global"))
    rows = (await session.execute(build_rank_statement(span, None if global_flag else group_id).limit(12))).all()
    scope_text, span_text = await get_scope_span_text(user_id, span, global_flag)
    title = await lang.text("bar.main_title", user_id, scope_text, span_text)
    subtitle = await lang.text("bar.subtitle_global", user_id) if global_flag else group_id
    image = await render_bar(
        [
            GroupChatterboxWithNickname(
                nickname=(await get_user(row.user_id)).get_nickname(), message_count=row.total_count
            )
            for row in rows
        ],
        user_id,
        title,
        subtitle,
    )
    if isinstance(bot, Bot_QQ):
        # QQ 官方：图片之后追加一条带跳转按钮的 markdown
        await send_rank_with_buttons(bot, event, user_id, span, global_flag, image)
        await chatterbox.finish()
    await chatterbox.finish(UniMessage().image(raw=image))


@recorder.handle()
async def _(session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()) -> None:
    async with open_file("disabled.json", FileType.CONFIG, []) as f:
        if group_id in f.data:
            await recorder.finish()
    today = date.today()
    result = await session.scalar(
        select(GroupChatterbox).where(
            GroupChatterbox.group_id == group_id,
            GroupChatterbox.user_id == user_id,
            GroupChatterbox.record_date == today,
        )
    )
    if result is None:
        result = GroupChatterbox(group_id=group_id, user_id=user_id, record_date=today, message_count=1)
    else:
        result.message_count += 1
    await session.merge(result)
    await session.commit()
    await recorder.finish()
