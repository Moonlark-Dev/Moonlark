from typing import Any
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

from nonebot_plugin_larklang.__main__ import LangHelper

from nonebot_plugin_larkuser import patch_matcher

alc = Alconna(
    "bag",
    Subcommand(
        "overflow",
        Subcommand("list"),
        Subcommand("show", Args["index", int]),
        Subcommand("get", Args["index", int], Args["count", int, 0]),
    ),
    Subcommand("show", Args["index", int]),
    Subcommand("drop", Args["index", int], Args["count", int, 0]),
    Subcommand("tidy"),
    Subcommand("move", Args["origin", int], Args["target", int], Args["count", int, 0]),
    # bag usage / bag use：展示物品的使用指令（QQ 平台附带可点击按钮）
    Subcommand("usage", Args["index?", int], alias=["use"]),
)
bag = on_alconna(alc)
patch_matcher(bag)
lang = LangHelper()
