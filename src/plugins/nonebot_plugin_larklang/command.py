from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna, Option
from nonebot_plugin_alconna.uniseg import UniMessage

from nonebot_plugin_larkutils.superuser import is_user_superuser
from nonebot_plugin_larkutils import get_user_id, get_group_id
from . import __main__ as main

lang_cmd = on_alconna(
    Alconna(
        "lang",
        Subcommand(
            "set",
            Args["language", str],
            Option("--group|-g"),
        ),
        Subcommand("view", Args["language", str]),
        Subcommand("reload"),
    ),
)
lang = main.LangHelper()


@lang_cmd.assign("reload")
async def _(bot: Bot, user_id: str = get_user_id(), superuser: bool = is_user_superuser()) -> None:
    if superuser:
        await main.load_languages()
        if isinstance(bot, QQBot):
            await lang_cmd.finish(
                UniMessage()
                .style(
                    await lang.text("reload.success_md", user_id),
                    "markdown",
                )
                .send(),
            )
        else:
            await lang.finish("reload.success", user_id)
    if isinstance(bot, QQBot):
        await lang_cmd.finish(
            UniMessage()
            .style(
                await lang.text("reload.no_permission_md", user_id),
                "markdown",
            )
            .send(),
        )
    await lang.finish("reload.no_permission", user_id)


@lang_cmd.assign("set")
async def _(
    bot: Bot,
    language: str,
    group: bool,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    if language not in main.get_languages():
        await lang.send("global.not_found", user_id, language)
    if group:
        await main.set_group_language(group_id, language)
        if isinstance(bot, QQBot):
            await lang_cmd.finish(
                UniMessage()
                .style(
                    await lang.text("set.group.success_md", user_id, language),
                    "markdown",
                )
                .send(),
            )
        else:
            await lang.send("set.group.success", user_id, language)
    else:
        await main.set_user_language(user_id, language)
        if isinstance(bot, QQBot):
            await lang_cmd.finish(
                UniMessage()
                .style(
                    await lang.text("set.success_md", user_id, language),
                    "markdown",
                )
                .send(),
            )
        else:
            await lang.send("set.success", user_id, language)
    await lang_cmd.finish()


@lang_cmd.assign("view")
async def _(bot: Bot, language: str, user_id: str = get_user_id()) -> None:
    if language not in main.get_languages():
        await lang.send("global.not_found", user_id, language)
    data = main.get_languages()[language]
    if isinstance(bot, QQBot):
        await lang_cmd.finish(
            UniMessage()
            .style(
                await lang.text(
                    "view.info_md",
                    user_id,
                    language,
                    data.author,
                    data.version,
                    data.display.description,
                ),
                "markdown",
            )
            .send(),
        )
    else:
        await lang.reply("view.info", user_id, language, data.author, data.version, data.display.description)


@lang_cmd.assign("$main")
async def _(bot: Bot, user_id: str = get_user_id()) -> None:
    if isinstance(bot, QQBot):
        items = [await lang.text("lang.item_md", user_id, lang_code, lang_code) for lang_code in main.get_languages()]
        await lang_cmd.finish(
            UniMessage()
            .style(
                await lang.text(
                    "lang.list_md",
                    user_id,
                    "\n".join(items),
                ),
                "markdown",
            )
            .send(),
        )
    else:
        await lang.reply("lang.list", user_id, "\n".join(list(main.get_languages())))
