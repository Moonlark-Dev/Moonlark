from typing import Any
from nonebot_plugin_alconna import Alconna, Args, MultiVar, Option, Subcommand, on_alconna

from ..nonebot_plugin_larkuser.matcher import patch_matcher

alc = Alconna(
    "bag",
    Subcommand(
        "overflow",
        Subcommand("show", Args["index", int]),
        Subcommand("get", Args["index", int], Args["count", int, 0])
    ),
    Subcommand("show", Args["index", int]),
    Subcommand("drop", Args["index", int], Args["count", int, 0]),
    Subcommand("tidy"),
    Subcommand("move", Args["origin", int], Args["to", int], Args["count", int, 0]),
    Subcommand(
        "use",
        Args["index", int],
        Option("--count|-c", Args["count", int, 1]),
        Args["argv", MultiVar(Any)]     # type: ignore
    )
)
bag = on_alconna(alc)
patch_matcher(bag)
