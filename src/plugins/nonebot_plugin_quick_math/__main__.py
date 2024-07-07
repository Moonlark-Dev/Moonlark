from typing import Literal
from nonebot_plugin_alconna import Alconna, Args, Option, Subcommand, on_alconna

from ..nonebot_plugin_larkuser.matcher import patch_matcher
from ..nonebot_plugin_larklang import LangHelper


quick_math = on_alconna(
    Alconna(
        "quick-math",
        Subcommand("rank", Args["rank_type", Literal["total", "max"], "max"]),
        Subcommand("award"),
    )
)
lang = LangHelper()
patch_matcher(quick_math)
