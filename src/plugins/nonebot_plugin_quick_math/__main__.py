from typing import Literal
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna, Option

from src.plugins.nonebot_plugin_larkuser.utils.matcher import patch_matcher
from ..nonebot_plugin_larklang import LangHelper


quick_math = on_alconna(
    Alconna(
        "quick-math",
        Subcommand("rank", Args["rank_type", Literal["total", "max"], "max"]),
        Subcommand("points"),
        Subcommand("exchange", Args["count?", int]),
        Option("--level|-l", Args["start_level", int, 1]),
    )
)
lang = LangHelper()
patch_matcher(quick_math)
