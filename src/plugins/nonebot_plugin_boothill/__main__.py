from nonebot import on_command
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from ..nonebot_plugin_larkutils.html import escape_html
from ..nonebot_plugin_larkutils.user import get_user_id
from ..nonebot_plugin_larklang.__main__ import LangHelper
from .censor import censor
from nonebot.adapters import Message
from nonebot.params import CommandArg

boothill = on_command("boothill")
lang = LangHelper()


@boothill.handle()
async def _(user_id: str = get_user_id(), content: Message = CommandArg()) -> None:
    text = content.extract_plain_text()
    await boothill.finish(await UniMessage().image(raw=await md_to_pic(
        md=await lang.text(
            "cmd.md",
            user_id,
            escape_html(censor(text)).replace("\n", "<br>").replace("<br><br>", "\n\n")
        )
    )).export(), reply_message=True)
