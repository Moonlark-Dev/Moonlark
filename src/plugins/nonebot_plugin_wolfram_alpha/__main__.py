from nonebot_plugin_alconna import Alconna, Args, MultiVar, UniMessage, on_alconna

from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils.user import get_user_id
from .exception import ApiError
from .wolfram import get_calc

alc = Alconna(
    "calc",
    Args["expr", MultiVar(str)],
)
calc = on_alconna(alc)
lang = LangHelper()


@calc.handle()
async def _(expr: list[str], user_id: str = get_user_id()) -> None:
    try:
        await calc.finish(UniMessage().image(raw=await get_calc(" ".join(expr))), reply_message=True)
    except ApiError:
        await lang.finish("calc.failed", user_id)
