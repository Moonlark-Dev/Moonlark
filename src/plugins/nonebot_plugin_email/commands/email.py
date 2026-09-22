from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage

from nonebot_plugin_render.render import render_template
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_larkutils.command import get_command_prefix
from ..utils.read import mark_email_read
from ..utils.unread import get_unread_email
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import email
from ..lang import lang


@email.assign("$main")
async def _(bot: Bot, user_id: str = get_user_id()) -> None:
    image = await render_template(
        "email.html.jinja",
        await lang.text("email_list.title", user_id),
        user_id,
        {
            "item_claimed": await lang.text("email_list.claimed", user_id),
            "email_list": [
                {
                    "subject": email["subject"],
                    "time": await lang.text("email_list.time", user_id, email["time"].strftime("%Y-%m-%d %H:%M:%S")),
                    "from": await lang.text("email_list.from", user_id, email["author"]),
                    "id": await lang.text("email_list.email_id", user_id, await mark_email_read(email["id"], user_id)),
                    "content": email["content"].replace("\n", "<br>"),
                    "is_claimed": email["is_claimed"],
                    "item_list": [
                        {
                            "name": await (
                                await get_item(
                                    get_location_by_id(item["item_id"]), user_id, item["count"], item["data"]
                                )
                            ).getName(),
                            "count": item["count"],
                        }
                        for item in email["items"]
                    ],
                }
                async for email in get_unread_email(user_id)
            ],
        },
    )
    if isinstance(bot, QQBot):
        # QQ 官方：邮件列表后附带「一键领取」「全部已读」按钮
        prefix = get_command_prefix()
        await (
            UniMessage()
            .image(raw=image)
            .keyboard(
                Button("enter", await lang.text("button.claim_all", user_id), text=f"{prefix}email claim all"),
                Button("enter", await lang.text("button.read_all", user_id), text=f"{prefix}email read all"),
            )
            .send()
        )
        await email.finish()
    await email.finish(UniMessage().image(raw=image))
