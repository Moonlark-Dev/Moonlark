from ...nonebot_plugin_larklang import LangHelper


lang = LangHelper()


def is_quit(
    message: str,
    keywords: list[str] = [
        "退出",
        "exit",
        "quit",
        "q",
    ],
) -> bool:
    return message.lower().strip() in keywords


async def parse_exit_input(message: str, user_id: str, **kwargs) -> None:
    if is_quit(message, **kwargs):
        await lang.finish("quit.exited", user_id)
