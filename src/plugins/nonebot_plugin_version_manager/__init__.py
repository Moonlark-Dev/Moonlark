from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-version-manager",
    description="Version management plugin for Moonlark",
    usage="Manage version using git and nb_cli, SUPERUSER only",
    config=Config,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")

from . import __main__ as __main__
