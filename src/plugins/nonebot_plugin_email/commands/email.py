from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import UniMessage

from nonebot_plugin_render.render import render_template
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_items.utils.get import get_item
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

    纯 markdown 展示邮件正文与附件物品，一键领取/全部已读以 <qqbot-cmd-input>
    形式内嵌，不再渲染邮件列表图片，也不附带键盘按钮。
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
    lines.extend(
        [
            await lang.text("email_list.action_claim_all_md", user_id),
            await lang.text("email_list.action_read_all_md", user_id),
            "",
            await lang.text("email_list.footer_md", user_id),
        ]
    )
    return "\n".join(lines)


@email.assign("$main")
async def _(bot: Bot, user_id: str = get_user_id()) -> None:
    email_list = await _collect_email_list(user_id)
    if isinstance(bot, QQBot):
        # QQ 官方：完全改用 markdown 文本展示，不用图床渲染图，也不发送键盘按钮，
        # 领取/已读操作内嵌在 markdown 的 <qqbot-cmd-input> 里
        await email.finish(UniMessage().style(await _build_markdown_email_list(user_id, email_list), "markdown"))
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
