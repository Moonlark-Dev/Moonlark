from pathlib import Path
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import template_to_pic

from ..utils.read import mark_email_read

from ..utils.unread import get_unread_email
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import email
from ..lang import lang


@email.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    image = await template_to_pic(
        Path(__file__).parent.parent.joinpath("templates").as_posix(),
        "list.html.jinja",
        {
            "title": await lang.text("email_list.title", user_id),
            "footer": await lang.text("email_list.footer", user_id),
            "email_list": [{
                "subject": email["subject"],
                "time": await lang.text("email_list.time", user_id, email["time"].strftime("%Y-%m-%d %H:%M:%S")),
                "from": await lang.text("email_list.from", user_id, email["author"]),
                "id": await lang.text("email_list.email_id", user_id, await mark_email_read(email["id"], user_id)),
                "content": email["content"].replace("\n", "<br>"),
                "item_list": []
            } async for email in get_unread_email(user_id)],
        }
    )
    await email.finish(UniMessage().image(raw=image))
