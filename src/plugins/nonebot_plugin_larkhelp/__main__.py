import aiofiles
from nonebot import get_driver
from ..nonebot_plugin_larklang.__main__ import LangHelper
from ..nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from .collector import collect_command_help



@get_driver().on_startup
async def _() -> None:
    global help_list
    help_list = await collect_command_help()

help_cmd = on_alconna(
    Alconna(
        "help",
        Args["command?", str]
    ),
    use_cmd_start=True
)
lang = LangHelper()


@help_cmd.assign("command")
async def _(command: str, user_id: str = get_user_id) -> None:
    if command not in help_list:
        await lang.finish("command.not_found", user_id, command)
    data = help_list[command]
    helper = LangHelper(data.plugin)
    await lang.reply(
        "command.info",
        user_id,
        command,
        await helper.text(data.information, user_id),
        "\n".join([
            await lang.text("command.usage", user_id, await helper.text(
                usage,
                user_id
            )) for usage in data.usages
        ])
    )
    await help_cmd.finish()

from jinja2 import Template
from pathlib import Path
from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_saa import Image, MessageFactory

@help_cmd.assign("$main")
async def _(user_id: str = get_user_id) -> None:
    template_path = Path(__file__).parent.joinpath("template/index.html.jinja")
    msg_builder = MessageFactory([Image(await template_to_pic(
        template_path.parent.as_posix(),
        template_path.name,
        dict(
            title=await lang.text("list.title", user_id),
            footer=await lang.text("list.footer", user_id),
            usages_text=await lang.text("list.usage_text", user_id),
            commands=[
                {
                    "name": name,
                    "description": await (plugin_lang := LangHelper(data.plugin)).text(data.description, user_id),
                    "information": await plugin_lang.text(data.information, user_id),
                    "usages": [
                        await lang.text("list.usage", user_id, await plugin_lang.text(usage, user_id)) for usage in data.usages
                    ]
                } for name, data in help_list.items()
            ]
    )), "image.png")])
    await msg_builder.finish()

    
