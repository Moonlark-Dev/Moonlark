import asyncio
import random
from nonebot.log import logger
import traceback
from unittest.util import sorted_list_difference
from nonebot_plugin_larklang.__main__ import load_languages
from pathlib import Path
import sys
from typing import Any, Optional

from nonebot import get_driver
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage

from nonebot_plugin_render.render import render_template
from nonebot_plugin_render.cache import creator

from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils import get_user_id
from .models import CommandHelp
from .collector import collect_command_help
from nonebot.exception import FinishedException

help_list = {}


@get_driver().on_startup
async def setup_help_list() -> None:
    global help_list
    help_list = await collect_command_help()


help_cmd = on_alconna(Alconna("help", Args["command?", str]))
lang = LangHelper()


def get_help_list() -> dict[str, CommandHelp]:
    return help_list


@help_cmd.assign("command")
async def _(command: str, user_id: str = get_user_id()) -> None:
    if command not in help_list:
        await lang.finish("command.not_found", user_id, command)
    data = help_list[command]
    helper = LangHelper(data.plugin)
    await lang.reply(
        "command.info",
        user_id,
        command,
        await helper.text(data.details, user_id),
        "\n".join(
            [await lang.text("command.usage", user_id, await helper.text(usage, user_id)) for usage in data.usages]
        ),
    )
    await help_cmd.finish()


async def get_help_dict(name: str, user_id: str, data: Optional[CommandHelp] = None) -> dict[str, str | list[str]]:
    data = data or help_list[name]
    return {
        "name": name,
        "description": await (plugin_lang := LangHelper(data.plugin)).text(data.description, user_id),
        "details": await plugin_lang.text(data.details, user_id),
        "category": data.category,
        "usages": [
            (await lang.text("list.usage", user_id, await plugin_lang.text(usage, user_id))) for usage in data.usages
        ],
    }


async def get_templates(user_id: str) -> list[dict[str, Any]]:
    if not help_list:
        raise ValueError("No Command")
    sorted_help_list = sorted(list(help_list.items()), key=lambda x: x[0])
    commands = []
    for command in [await get_help_dict(name, user_id, data) for name, data in sorted_help_list if data.category != "superuser"]:
        for category in commands:
            if category["name"] == command["category"]:
                category["commands"].append(command)
                break
        else:
            commands.append({"name": command["category"], "commands": [command]})
    for category in commands:
        category["name"] = await lang.text(f"list.category.{category['name']}", user_id)
    return commands


async def generate_markdown() -> str:
    await setup_help_list()
    await load_languages()
    user_id = f"mlsid::--lang={sys.argv[1]}"
    text = await lang.text("markdown.title", user_id)
    commands = []
    for command_list in [category["commands"] for category in (await get_templates(user_id))]:
        commands.extend(command_list)
    for command in commands:
        text += await lang.text(
            "markdown.command", user_id, command["name"], command["description"], command["details"]
        )
        for usage in command["usages"]:
            text += await lang.text("markdown.usage", user_id, usage)
    return text


def generate_help_markdown() -> None:
    # nb larkhelp-generate <lang> <file>
    with open(Path(sys.argv[2]), "w", encoding="utf-8") as f:
        f.write(asyncio.run(generate_markdown()))


@creator("help.html.jinja")
async def render(user_id: str) -> bytes:
    return await render_template(
        "help.html.jinja",
        await lang.text("list.title", user_id),
        user_id,
        {"categories": await get_templates(user_id), "len": len},
        {"usage_text": await lang.text("list.usage_text", user_id)},
        True,
        True,
    )


@help_cmd.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    try:
        await help_cmd.finish(
            UniMessage().image(
                raw=await render(user_id),
                name="image.png",
            )
        )
    except FinishedException:
        raise
    except Exception:
        logger.error(traceback.format_exc())
        await help_cmd.finish(await lang.text("command.error", user_id))


async def get_menu_templates(user_id: str) -> list[dict[str, Any]]:
    """获取菜单所需的所有分类数据，包括 superuser"""
    if not help_list:
        raise ValueError("No Command")
    sorted_help_list = sorted(list(help_list.items()), key=lambda x: x[0])
    categories: dict[str, dict] = {}
    for name, data in sorted_help_list:
        cat_id = data.category
        if cat_id not in categories:
            categories[cat_id] = {"id": cat_id, "commands": []}
        cmd_dict = await get_help_dict(name, user_id, data)
        categories[cat_id]["commands"].append(cmd_dict)

    result = []
    for cat_id, cat_data in categories.items():
        cat_data["name"] = await lang.text(f"list.category.{cat_id}", user_id)
        cat_data["count"] = len(cat_data["commands"])
        result.append(cat_data)
    return result


async def get_random_command(user_id: str) -> dict:
    """随机指令（排除 superuser）"""
    non_super = {name: data for name, data in help_list.items() if data.category != "superuser"}
    if not non_super:
        raise ValueError("No non-superuser commands")
    name = random.choice(list(non_super.keys()))
    return await get_help_dict(name, user_id, non_super[name])


async def get_category_commands(category_id: str, user_id: str) -> Optional[dict]:
    """获取指定分类的指令数据"""
    commands = []
    for name, data in sorted(help_list.items(), key=lambda x: x[0]):
        if data.category == category_id:
            commands.append(await get_help_dict(name, user_id, data))
    if not commands:
        return None
    return {
        "id": category_id,
        "name": await lang.text(f"list.category.{category_id}", user_id),
        "commands": commands,
        "count": len(commands),
    }


async def render_menu(user_id: str) -> bytes:
    categories = await get_menu_templates(user_id)
    random_cmd = await get_random_command(user_id)
    return await render_template(
        "menu.html.jinja",
        await lang.text("menu.title", user_id),
        user_id,
        {"categories": categories, "random_command": random_cmd},
        {
            "menu_category_hint": await lang.text("menu.menu_category_hint", user_id),
            "random_title": await lang.text("menu.random_title", user_id),
        },
        True,
        True,
    )


menu_cmd = on_alconna(Alconna("menu", Args["category?", str]))


@menu_cmd.assign("category")
async def menu_category_handler(category: str, user_id: str = get_user_id()) -> None:
    cat_data = await get_category_commands(category, user_id)
    if cat_data is None:
        await lang.finish("menu.category_not_found", user_id, category)
    try:
        await menu_cmd.finish(
            UniMessage().image(
                raw=await render_template(
                    "menu_category.html.jinja",
                    cat_data["name"],
                    user_id,
                    cat_data,
                    {"help_hint": await lang.text("menu.menu_cat_help_hint", user_id)},
                    False,
                    True,
                ),
                name="image.png",
            )
        )
    except FinishedException:
        raise
    except Exception:
        logger.error(traceback.format_exc())
        await menu_cmd.finish(await lang.text("command.error", user_id))


@menu_cmd.assign("$main")
async def menu_main_handler(user_id: str = get_user_id()) -> None:
    try:
        await menu_cmd.finish(
            UniMessage().image(
                raw=await render_menu(user_id),
                name="image.png",
            )
        )
    except FinishedException:
        raise
    except Exception:
        logger.error(traceback.format_exc())
        await menu_cmd.finish(await lang.text("command.error", user_id))
