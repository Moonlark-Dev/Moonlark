from typing import Literal
from nonebot_plugin_alconna import Alconna, Args, Option, Subcommand, on_alconna
from ..nonebot_plugin_larklang import LangHelper


quick_math = on_alconna(Alconna(
    "quick-math",
    Subcommand("rank", Args["rank_type", Literal["total", "max"], "max"]),
    Subcommand("award", Option("--claim|-c")),
))
lang = LangHelper()
