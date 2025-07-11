from typing import Literal
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna, Option

from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larklang import LangHelper


quick_math = on_alconna(
    Alconna(
        "quick-math",
        Subcommand("rank", Option("-t|--total")),
        Subcommand("points"),
        Subcommand("--level", Args["max_level", int]),
        Subcommand("zen", Args["zen_level", int]),
    ),
    aliases={"qm"},
)
lang = LangHelper()
patch_matcher(quick_math)
