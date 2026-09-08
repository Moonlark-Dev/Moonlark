from nonebot_plugin_alconna import Alconna, Args, Option, Subcommand, on_alconna

from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larklang import LangHelper

quick_math = on_alconna(
    Alconna(
        "quick-math",
        Subcommand("start", Option("--level", Args["max_level", int])),
        Subcommand("rank", Option("-t|--total")),
        Subcommand("points"),
        Subcommand("zen", Args["zen_level", int]),
        Subcommand(
            "pvp",
            Subcommand("create", Args["max_players", int, 5]),
            Subcommand("join", Args["room_id", str]),
            Subcommand("quit"),
            Subcommand("start"),
        ),
    ),
    aliases={"qm"},
)
lang = LangHelper()
patch_matcher(quick_math)
