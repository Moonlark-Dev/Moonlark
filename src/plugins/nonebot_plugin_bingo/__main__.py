from nonebot_plugin_alconna import Alconna, Args, on_alconna, UniMessage
from nonebot_plugin_waiter import prompt
from src.plugins.nonebot_plugin_larklang import LangHelper
from src.plugins.nonebot_plugin_larkuser import get_user
from src.plugins.nonebot_plugin_larkutils import get_user_id, review_text
from src.plugins.nonebot_plugin_render import render_template
from .config import config

alc = Alconna("bingo", Args["width", int, 5], Args["height", int, 5])
matcher = on_alconna(alc)
lang = LangHelper()


async def create_empty_list(width: int, height: int, user_id: str) -> list[list[str]]:
    if width <= 0 or height <= 0:
        await lang.finish("bingo.too_small", user_id)
    if width * height > config.bingo_max_prompt_count:
        await lang.finish("bingo.too_big", user_id)
    return [["" for _ in range(width)] for _ in range(height)]


async def get_input(p: str) -> str:
    while (result := await prompt(p)) is None:
        pass
    return result.extract_plain_text()


def get_review_string(title: str, desc: str, table: list[list[str]]) -> str:
    string = f"{title}\n{desc}\n"
    for r in table:
        for c in r:
            string += f"{c}\n"
    return string


@matcher.handle()
async def _(width: int, height: int, user_id: str = get_user_id()) -> None:
    table = await create_empty_list(width, height, user_id)
    title = await get_input(await lang.text("prompt.title", user_id))
    description = await get_input(await lang.text("prompt.description", user_id))
    for r in range(height):
        for c in range(width):
            i = await get_input(
                await lang.text("prompt.item", user_id, r + 1, c + 1, r * width + c + 1, width * height)
            )
            if i == "quit":
                await lang.finish("bingo.quit", user_id)
            table[r][c] = i
    result = await review_text(get_review_string(title, description, table))
    if not result["compliance"]:
        await lang.finish("bingo.review_failed", user_id, result["message"])
    image = await render_template(
        "bingo.html.jinja",
        title,
        user_id,
        {
            "description": description,
            "items": table,
            "maker": await lang.text("bingo.maker", user_id, (await get_user(user_id)).get_nickname()),
        },
    )
    message = UniMessage().image(raw=image)
    await matcher.finish(message)
