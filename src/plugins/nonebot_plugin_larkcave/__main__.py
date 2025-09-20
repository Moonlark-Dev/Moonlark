from typing import Union
from nonebot_plugin_alconna import Alconna, Args, Image, MultiVar, Option, Subcommand, Text, on_alconna

alc = Alconna(
    "cave",
    Subcommand(
        "a|add",
        Args["content", MultiVar(Union[Image, Text])],  # type: ignore
    ),
    Subcommand(
        "s|restore",
        Args["cave_id", int],
    ),
    Subcommand(
        "g|get",
        Args["cave_id", int],
    ),
    Subcommand("s|statisics"),
    Subcommand("r|remove", Option("-c|--comment", Args["comment_id", int]), Args["cave_id?", int]),
    Subcommand("c|cd", Option("-s|--set", Args["time", float]), Option("-u|--user")),
    separators=["-", " "],
)
cave = on_alconna(alc, use_cmd_start=True, skip_for_unmatch=False)
