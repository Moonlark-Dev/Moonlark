from pathlib import Path
import nonebot
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-minigames",
    description="",
    usage="",
    config=None,
)

sub_plugins = nonebot.load_plugins(
    str(Path(__file__).parent.joinpath("plugins").resolve())
)

nonebot.require("nonebot_plugin_alconna")
nonebot.require("nonebot_plugin_minigames:nonebot_plugin_minigames_api")
nonebot.require("nonebot_plugin_render")
nonebot.require("nonebot_plugin_larkutils")
nonebot.require("nonebot_plugin_larklang")

from . import __main__
