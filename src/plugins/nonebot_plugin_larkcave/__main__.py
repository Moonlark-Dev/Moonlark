from .model import CaveData, ImageData
from nonebot_plugin_alconna import Alconna, Args, Image, MultiVar, UniMessage, Subcommand, on_alconna, Text, Image
from typing import Union


alc = Alconna(
    "cave",
    Subcommand(
        "a|add",
        Args["content", MultiVar(Union[Image, Text])], # type: ignore
    ),
    separators="-"
)
cave = on_alconna(
    alc,
    use_cmd_start=True
)
