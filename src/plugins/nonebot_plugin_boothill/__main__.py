from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot_plugin_alconna import UniMessage

from ..nonebot_plugin_render.render import render_template
from ..nonebot_plugin_larklang.__main__ import LangHelper
from ..nonebot_plugin_larkutils.user import get_user_id
from .censor import censor

boothill = on_command("boothill")
lang = LangHelper()


@boothill.handle()
async def _(user_id: str = get_user_id(), content: Message = CommandArg()) -> None:
    text = content.extract_plain_text()
    await boothill.finish(
        await UniMessage()
        .image(
            raw=await render_template(
                "boothill.html.jinja",
                await lang.text("image.title", user_id),
                user_id,
                {
                    "content": censor(text),
                },
            )
        )
        .export(),
        reply_message=True,
    )
