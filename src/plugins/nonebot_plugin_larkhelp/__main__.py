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
        await helper.text(data.description, user_id),
        "" if data.information is None else f"\n{await helper.text(data.description, user_id)}\n",
        "\n".join([
            await lang.text("command.usage", user_id, await helper.text(
                usage,
                user_id
            )) for usage in data.usages
        ])
    )
    await help_cmd.finish()