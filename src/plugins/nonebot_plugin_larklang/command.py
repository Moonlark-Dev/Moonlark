from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

from nonebot_plugin_larkutils.superuser import is_user_superuser
from nonebot_plugin_larkutils import get_user_id
from . import __main__ as main

lang_cmd = on_alconna(
    Alconna(
        "lang",
        Subcommand(
            "set",
            Args["language", str],
        ),
        Subcommand("view", Args["language", str]),
        Subcommand("reload"),
    )
)
lang = main.LangHelper()


@lang_cmd.assign("reload")
async def _(user_id: str = get_user_id(), superuser: bool = is_user_superuser()) -> None:
    if superuser:
        await main.load_languages()
        await lang.finish("reload.success", user_id)
    await lang.finish("reload.no_permission", user_id)


@lang_cmd.assign("set")
async def _(language: str, user_id: str = get_user_id()) -> None:
    if language not in main.get_languages():
        await lang.send("global.not_found", user_id, language)
    await main.set_user_language(user_id, language)
    await lang.send("set.success", user_id, language)
    await lang_cmd.finish()


@lang_cmd.assign("view")
async def _(language: str, user_id: str = get_user_id()) -> None:
    if language not in main.get_languages():
        await lang.send("global.not_found", user_id, language)
    data = main.get_languages()[language]
    await lang.reply("view.info", user_id, language, data.author, data.version, data.display.description)


@lang_cmd.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    await lang.reply("lang.list", user_id, "\n".join(list(main.get_languages().keys())))
