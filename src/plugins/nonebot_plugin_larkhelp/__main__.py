import asyncio
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
    for command in [await get_help_dict(name, user_id, data) for name, data in sorted_help_list]:
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
        {"categories": await get_templates(user_id)},
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
        await help_cmd.finish(await lang.text("command.error", user_id))
