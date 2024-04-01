from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_larklang",
    description="Moonlark 本地化插件",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

