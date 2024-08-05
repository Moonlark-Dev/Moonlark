from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg

from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id, review_text
from ..nonebot_plugin_render.render import render_template

from nonebot_plugin_alconna import UniMessage

latex = on_command("latex")
lang = LangHelper()


@latex.handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    text = message.extract_plain_text()
    if text and not (result := await review_text(text))["compliance"]:
        await lang.finish("latex.review_fail", user_id, str(result["message"]), reply_message=True)
    if "\n" not in text and not text.startswith("$"):
        text = f"$ {text} $"
    await latex.finish(
        await UniMessage()
        .image(
            raw=await render_template(
                "latex.html.jinja", await lang.text("latex.title", user_id), user_id, {"latex_content": text}
            )
        )
        .export()
    )
