from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage

from nonebot_plugin_render.render import render_template
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_larkutils.command import get_command_prefix
from nonebot_plugin_larkutils.user import get_user_id
from ..utils.read import mark_email_read
from ..utils.unread import get_unread_email
from ..__main__ import email
from ..lang import lang


async def _collect_email_list(user_id: str) -> list[dict]:
    """收集未读邮件并按展示格式转换（列出即标记已读）

    Returns:
        邮件信息字典列表，字段：subject、time、author、id、content、is_claimed、item_list
    """
    email_list: list[dict] = []
    async for data in get_unread_email(user_id):
        email_list.append(
            {
                "subject": data["subject"],
                "time": data["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "author": data["author"],
                "id": await mark_email_read(data["id"], user_id),
                "content": data["content"],
                "is_claimed": data["is_claimed"],
                "item_list": [
                    {
                        "name": await (
                            await get_item(get_location_by_id(item["item_id"]), user_id, item["count"], item["data"])
                        ).getName(),
                        "count": item["count"],
                    }
                    for item in data["items"]
                ],
            }
        )
    return email_list


async def _build_markdown_email_list(user_id: str, email_list: list[dict]) -> str:
    """构建 QQ 官方机器人的邮件列表 markdown

    纯 markdown 展示邮件正文与附件物品，不再渲染邮件列表图片；一键领取/全部已读
    由键盘按钮承载，因此这里既不内嵌 <qqbot-cmd-input>，也不展示用法说明。
    """
    lines = [await lang.text("email_list.title_md", user_id, len(email_list)), ""]
    if not email_list:
        lines.append(await lang.text("email_list.empty", user_id))
    for data in email_list:
        lines.append(await lang.text("email_list.subject_md", user_id, data["subject"]))
        lines.append(await lang.text("email_list.time", user_id, data["time"]))
        lines.append(await lang.text("email_list.from", user_id, data["author"]))
        lines.append(await lang.text("email_list.email_id", user_id, data["id"]))
        if data["content"]:
            lines.extend(["", data["content"]])
        if data["item_list"]:
            lines.extend(["", await lang.text("email_list.items", user_id)])
            if data["is_claimed"]:
                lines.append(await lang.text("email_list.claimed_md", user_id))
            for item in data["item_list"]:
                lines.append(await lang.text("email_list.item_md", user_id, item["name"], item["count"]))
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


@email.assign("$main")
async def _(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    email_list = await _collect_email_list(user_id)
    if isinstance(bot, QQBot):
        # QQ 官方：markdown 文本展示邮件，一键领取/全部已读改用键盘按钮下发
        # （带 keyboard 的消息走 UniMessage.send，之后再单独 finish 结束处理器）
        prefix = get_command_prefix()
        message = (
            UniMessage()
            .style(await _build_markdown_email_list(user_id, email_list), "markdown")
            .keyboard(
                Button("enter", await lang.text("button.claim_all", user_id), text=f"{prefix}email claim all"),
                Button("enter", await lang.text("button.read_all", user_id), text=f"{prefix}email read all"),
            )
        )
        await message.send(target=event, bot=bot)
        await email.finish()
    image = await render_template(
        "email.html.jinja",
        await lang.text("email_list.title", user_id),
        user_id,
        {
            "item_claimed": await lang.text("email_list.claimed", user_id),
            "email_list": [
                {
                    "subject": data["subject"],
                    "time": await lang.text("email_list.time", user_id, data["time"]),
                    "from": await lang.text("email_list.from", user_id, data["author"]),
                    "id": await lang.text("email_list.email_id", user_id, data["id"]),
                    "content": data["content"].replace("\n", "<br>"),
                    "is_claimed": data["is_claimed"],
                    "item_list": [{"name": item["name"], "count": item["count"]} for item in data["item_list"]],
                }
                for data in email_list
            ],
        },
    )
    await email.finish(UniMessage().image(raw=image))
