import traceback
from pathlib import Path

import aiofiles
import yaml
from nonebot import get_loaded_plugins, logger
from nonebot.plugin import Plugin

from .model import *


async def get_plugin_help(plugin: Plugin) -> dict[str, CommandHelp]:
    if plugin.module.__file__ is None:
        return {}
    path = Path(plugin.module.__file__).parent
    if not path.joinpath("help.yaml").exists():
        # logger.warning(f"插件 {plugin.name} 下没有 help.yaml 文件！")
        return {}
    async with aiofiles.open(path.joinpath("help.yaml"), encoding="utf-8") as f:
        data = CommandHelpData(**yaml.safe_load(await f.read()))
    help_list = {}
    for key, value in data.commands.items():
        help_list[key] = CommandHelp(**data.commands[key], plugin=data.plugin)
    return help_list


async def collect_command_help() -> dict[str, CommandHelp]:
    help_list = {}
    for plugin in get_loaded_plugins():
        try:
            help_list.update(await get_plugin_help(plugin))
        except Exception:
            logger.warning(f"获取插件帮助失败: {traceback.format_exc()}")
    return help_list
