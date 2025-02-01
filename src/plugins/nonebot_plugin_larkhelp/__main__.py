import asyncio
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
        "usages": [
            (await lang.text("list.usage", user_id, await plugin_lang.text(usage, user_id))) for usage in data.usages
        ],
    }


async def get_templates(user_id: str) -> dict[str, Any]:
    if not help_list:
        raise ValueError("No Command")
    return dict(
        usages_text=await lang.text("list.usage_text", user_id),
        commands=[await get_help_dict(name, user_id, data) for name, data in help_list.items()],
    )


async def generate_markdown() -> str:
    await setup_help_list()
    await load_languages()
    user_id = f"mlsid::--lang={sys.argv[1]}"
    text = await lang.text("markdown.title", user_id)
    for command in (await get_templates(user_id))["commands"]:
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
        "help.html.jinja", await lang.text("list.title", user_id), user_id, await get_templates(user_id), True
    )


@help_cmd.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    await help_cmd.finish(
        UniMessage().image(
            raw=await render(user_id),
            name="image.png",
        )
    )
