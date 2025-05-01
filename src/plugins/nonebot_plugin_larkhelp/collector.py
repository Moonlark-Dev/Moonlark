import traceback
from pathlib import Path

import aiofiles
import yaml
from nonebot import get_loaded_plugins, logger
from nonebot.compat import type_validate_python
from nonebot.plugin import Plugin

from .models import *


async def get_plugin_help(plugin: Plugin) -> dict[str, CommandHelp]:
    if plugin.module.__file__ is None:
        return {}
    path = Path(plugin.module.__file__).parent
    if not path.joinpath("help.yaml").exists():
        return {}
    async with aiofiles.open(path.joinpath("help.yaml"), encoding="utf-8") as f:
        data = type_validate_python(CommandHelpData, yaml.safe_load(await f.read()))
    help_list = {}
    for key, value in data.commands.items():
        if isinstance(value, str):
            l = value.split(";")
            usage_count = l[1]
            value = l[0] or "help"
            if usage_count.isdigit():
                usage_count = int(usage_count)
            else:
                usage_count = 1
            if len(l) > 2:
                category = l[-1]
            else:
                category = "new"
            help_list[key] = CommandHelp(
                plugin=data.plugin,
                description=f"{value}.description",
                details=f"{value}.details",
                usages=[f"{value}.usage{i}" for i in range(1, usage_count + 1)],
                category=category,
            )
        else:
            help_list[key] = CommandHelp(**value, plugin=data.plugin)
    return help_list


async def collect_command_help() -> dict[str, CommandHelp]:
    help_list = {}
    for plugin in get_loaded_plugins():
        try:
            help_list.update(await get_plugin_help(plugin))
        except Exception:
            logger.warning(f"获取插件帮助失败: {traceback.format_exc()}")
    return help_list
