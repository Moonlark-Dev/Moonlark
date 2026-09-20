"""`/buff` 指令：查看当前附着的 buff 列表与详情。"""

from typing import Optional

from nonebot_plugin_alconna import Alconna, Args, on_alconna

from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id

from .api import BuffInfo, get_buff_attachment, get_buff_attachments
from .lang import lang
from .registry import BuffDefinition

alc = Alconna("buff", Args["buff_id?", str])
buff = on_alconna(alc)


def get_helper(definition: Optional[BuffDefinition]) -> LangHelper:
    """按 buff 定义所属插件选择语言助手"""
    if definition is not None and definition.lang_plugin and definition.lang_plugin != "buff":
        return LangHelper(definition.lang_plugin)
    return lang


async def get_name(attachment: BuffInfo, user_id: str) -> str:
    definition = attachment.definition
    if definition is None:
        return attachment.buff_id
    return await get_helper(definition).text(definition.name_key, user_id)


def get_max_layers(attachment: BuffInfo) -> int:
    definition = attachment.definition
    return max(definition.max_layers, 1) if definition is not None else 1


async def format_duration(seconds: float, user_id: str) -> str:
    """把剩余秒数格式化成可读文本"""
    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return await lang.text("duration.hour_minute", user_id, hours, minutes)
    if minutes:
        return await lang.text("duration.minute_second", user_id, minutes, secs)
    return await lang.text("duration.second", user_id, secs)


async def build_status_text(attachment: BuffInfo, user_id: str) -> str:
    """构建「剩余时间 / 剩余次数」的括号说明"""
    remaining = attachment.remaining_seconds
    if remaining is not None:
        duration_text = await format_duration(remaining, user_id)
        if attachment.remaining_count is not None:
            return await lang.text("status.both", user_id, duration_text, attachment.remaining_count)
        return await lang.text("status.duration", user_id, duration_text)
    if attachment.remaining_count is not None:
        return await lang.text("status.count", user_id, attachment.remaining_count)
    return await lang.text("status.none", user_id)


async def build_list_item(attachment: BuffInfo, user_id: str) -> str:
    return await lang.text(
        "list.item",
        user_id,
        await get_name(attachment, user_id),
        attachment.layers,
        get_max_layers(attachment),
        await build_status_text(attachment, user_id),
    )


async def build_detail(attachment: BuffInfo, user_id: str) -> str:
    definition = attachment.definition
    lines = [
        await lang.text(
            "info.header",
            user_id,
            await get_name(attachment, user_id),
            attachment.layers,
            get_max_layers(attachment),
        )
    ]
    if definition is not None and definition.description_key:
        lines.append(
            await lang.text(
                "info.description", user_id, await get_helper(definition).text(definition.description_key, user_id)
            )
        )
    remaining = attachment.remaining_seconds
    if remaining is None:
        lines.append(await lang.text("info.no_duration", user_id))
    else:
        lines.append(await lang.text("info.duration", user_id, await format_duration(remaining, user_id)))
    if attachment.remaining_count is None:
        lines.append(await lang.text("info.no_count", user_id))
    else:
        lines.append(await lang.text("info.count", user_id, attachment.remaining_count))
    lines.append(await lang.text("info.attached_at", user_id, attachment.created_at.strftime("%Y-%m-%d %H:%M:%S")))
    return "\n".join(lines)


@buff.handle()
async def _(buff_id: Optional[str] = None, user_id: str = get_user_id()) -> None:
    if buff_id:
        attachment = await get_buff_attachment(user_id, buff_id)
        if attachment is None:
            await lang.finish("info.not_found", user_id, buff_id)
        await buff.finish(await build_detail(attachment, user_id))

    attachments = await get_buff_attachments(user_id)
    if not attachments:
        await lang.finish("list.empty", user_id)
    lines = [await lang.text("list.title", user_id)]
    for attachment in attachments:
        lines.append(await build_list_item(attachment, user_id))
    await buff.finish("\n".join(lines))
