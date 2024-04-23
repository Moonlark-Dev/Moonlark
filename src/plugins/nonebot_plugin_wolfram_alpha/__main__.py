from nonebot_plugin_alconna import (
    MultiVar,
    UniMessage,
    on_alconna,
    Alconna,
    Args
)
from ..nonebot_plugin_larklang import LangHelper
from .exception import ApiError
from .wolfram import get_calc
from ..nonebot_plugin_larkutils.user import get_user_id

alc = Alconna(
    "calc",
    Args["expr", MultiVar(str)],
)
calc = on_alconna(alc)
lang = LangHelper()

@calc.handle()
async def _(expr: list[str], user_id: str = get_user_id()) -> None:
    try:
        await calc.finish(
            UniMessage().image(
                raw=await get_calc(" ".join(expr))
            ),
            reply_message=True
        )
    except ApiError:
        await lang.finish("calc.failed", user_id)
