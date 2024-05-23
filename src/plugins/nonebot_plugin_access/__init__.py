from nonebot.plugin import PluginMetadata
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_access",
    description="",
    usage="",
    config=Config,
)


from . import rule
