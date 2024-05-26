from nonebot_plugin_alconna import Alconna, Args, Match, MultiVar, UniMessage, on_alconna
from nonebot_plugin_htmlrender import md_to_pic

from ..nonebot_plugin_larkutils.html import escape_html

from ..nonebot_plugin_larkutils.user import get_user_id

from ..nonebot_plugin_larklang.__main__ import LangHelper

from .censor import censor

alc = Alconna(
    "boothill",
    Args["content", MultiVar(str)]
)
boothill = on_alconna(alc)
lang = LangHelper()


@boothill.handle()
async def _(content: list[str], user_id: str = get_user_id()) -> None:
    text = " ".join(content)
    await boothill.finish(UniMessage().image(raw=await md_to_pic(
        md=await lang.text(
            "cmd.md",
            user_id,
            escape_html(censor(text))
        )
    )), reply_message=True)
