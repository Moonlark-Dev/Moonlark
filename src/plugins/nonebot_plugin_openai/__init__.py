from nonebot import require, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.log import logger

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-openai",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_status_report")
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")

from nonebot_plugin_localstore import get_data_file

from . import models  # noqa: F401 - 确保 ORM 模型被注册
from .utils.chat import fetch_message, MessageFetcher
from .utils.message import generate_message
from .commands import model as _  # noqa: F401

driver = get_driver()


@driver.on_startup
async def migrate_json_to_db() -> None:
    """
    启动时迁移旧版 JSON 配置到数据库
    只在首次启动时执行，迁移完成后备份原文件
    """
    import json
    from pathlib import Path

    # 获取旧配置文件路径（使用 localstore 的路径）
    old_config_file = get_data_file("nonebot_plugin_openai", "model_config.json")

    if not old_config_file.exists():
        return  # 没有旧配置，无需迁移

    try:
        from .utils.model_config import set_default_model, set_model_for_identify

        with open(old_config_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 迁移默认模型
        default_model = data.get("default_model")
        if default_model:
            await set_default_model(default_model)
            logger.info(f"[OpenAI] 已迁移默认模型配置: {default_model}")

        # 迁移应用特定配置
        model_override = data.get("model_override", {})
        for identify, model in model_override.items():
            await set_model_for_identify(identify, model)
            logger.info(f"[OpenAI] 已迁移应用配置: {identify} -> {model}")

        # 迁移完成后备份原文件
        backup_file = old_config_file.with_suffix(".json.backup")
        old_config_file.rename(backup_file)
        logger.info(f"[OpenAI] 配置迁移完成，原文件已备份到: {backup_file}")

    except Exception as e:
        logger.error(f"[OpenAI] 配置迁移失败: {e}")
