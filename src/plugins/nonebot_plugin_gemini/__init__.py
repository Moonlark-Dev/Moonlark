from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-gemini",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_alconna")

from . import models  # noqa: F401 - 确保 ORM 模型被注册
from .utils.chat import fetch_message, fetch_json, MessageFetcher, strip_json_codeblock
from .utils.convert import convert_messages, decode_data_url, image_part_indices, is_image_part
from .utils.functions import create_function_list, generate_function_list
from .utils.message import generate_message, get_message, get_message_text, get_messages
from .utils.model_config import get_default_model, get_model_for_identify
from .commands import model as _  # noqa: F401
