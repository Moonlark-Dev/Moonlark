from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_cave_similarity_check",
    description="",
    usage="",
    config=Config,
)



from .text import check_text_content
from .image import check_image
