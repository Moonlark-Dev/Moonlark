import traceback

from nonebot import get_driver, logger
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, MultiVar, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_larklang.__main__ import LangHelper, load_languages
from nonebot_plugin_larkhelp.__main__ import get_menu_templates, get_templates, setup_help_list
from nonebot_plugin_larkhelp.__main__ import lang as larkhelp_lang
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_openai import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message, get_message_text

commands_markdown: str = ""


@get_driver().on_startup
async def setup_commands_markdown() -> None:
    global commands_markdown
    try:
        commands_markdown = await generate_commands_markdown()
        logger.info(f"command_helper: 已生成指令列表缓存（{len(commands_markdown)} 字符）")
    except Exception:
        logger.warning(f"command_helper: 指令列表生成失败，将在首次使用时重试\n{traceback.format_exc()}")


async def generate_commands_markdown() -> str:
    """动态生成与 COMMANDS.md 相同格式的指令列表 markdown（不读取仓库文件）"""
    await setup_help_list()
    await load_languages()
    user_id = "mlsid::--lang=zh_hans"
    text = await larkhelp_lang.text("markdown.title", user_id) + "\n"
    # 普通指令（不含 superuser）
    commands = []
    for command_list in [category["commands"] for category in (await get_templates(user_id))]:
        commands.extend(command_list)
    for command in commands:
        text += (
            await larkhelp_lang.text(
                "markdown.command",
                user_id,
                command["name"],
                command["description"],
                command["details"],
            )
            + "\n\n"
        )
        for usage in command["usages"]:
            text += await larkhelp_lang.text("markdown.usage", user_id, usage) + "\n"
    # superuser 指令（带管理员警告）
    for category in await get_menu_templates(user_id):
        if category["id"] == "superuser":
            for command in category["commands"]:
                text += (
                    await larkhelp_lang.text(
                        "markdown.command",
                        user_id,
                        command["name"],
                        command["description"],
                        command["details"],
                    )
                    + "\n\n"
                )
                text += await larkhelp_lang.text("markdown.superuser_warning", user_id) + "\n"
                for usage in command["usages"]:
                    text += await larkhelp_lang.text("markdown.usage", user_id, usage) + "\n"
            break
    return text


async def get_commands_markdown() -> str:
    """获取指令列表 markdown（有缓存用缓存，无缓存则生成）"""
    global commands_markdown
    if not commands_markdown:
        commands_markdown = await generate_commands_markdown()
    return commands_markdown


lang = LangHelper()


command_cmd = on_alconna(
    Alconna(
        "command",
        Args["query?", MultiVar(str)],
    ),
    use_cmd_start=True,
)


@command_cmd.handle()
async def handle_command(bot: Bot, query: tuple[str, ...], user_id: str = get_user_id()) -> None:
    if not query:
        await lang.finish("usage", user_id)
    query_text = " ".join(query)
    await lang.send("thinking", user_id)
    try:
        markdown = await get_commands_markdown()
    except Exception:
        logger.error(f"获取指令列表失败: {traceback.format_exc()}")
        await lang.finish("commands_error", user_id)
    system_prompt = await get_message_text("command_helper.md.jinja", markdown=markdown)
    try:
        fetcher = await MessageFetcher.create(
            [
                generate_message(system_prompt, "system"),
                generate_message(query_text, "user"),
            ],
            use_default_message=False,
            identify="Command Helper",
        )
        result = await fetcher.fetch_last_message()
    except Exception:
        logger.error(f"LLM 生成指令用法失败: {traceback.format_exc()}")
        await lang.finish("llm_error", user_id)
    if isinstance(bot, QQBot):
        await command_cmd.finish(
            UniMessage()
            .style(
                await lang.text("result_md", user_id, result),
                "markdown",
            )
            .send(),
        )
    else:
        await lang.finish("result", user_id, result)
