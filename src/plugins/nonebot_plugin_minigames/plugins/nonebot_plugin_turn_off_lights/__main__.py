from .config import config
from nonebot.log import logger
import re
from nonebot_plugin_waiter import prompt
import math
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from src.plugins.nonebot_plugin_larklang import LangHelper
from src.plugins.nonebot_plugin_larkutils import get_user_id
from .utils.generator import generate_map, change_light_stats
from .utils.image import draw
from ..nonebot_plugin_minigames_api import create_minigame_session


alc = Alconna("tol", Args["width", int, config.tol_default_size[1]], Args["height", int, config.tol_default_size[0]])
matcher = on_alconna(alc)
lang = LangHelper()


def get_all_lights_stats(game_map: list[list[bool]]) -> list[bool]:
    lights = []
    for r in game_map:
        lights.extend(r)
    logger.debug(str(lights))
    return lights


@matcher.handle()
async def _(width: int, height: int, user_id: str = get_user_id()) -> None:
    if not (1 <= width <= 9 and 1 <= height <= 9):
        await lang.finish("tol.size_error", user_id)
    game_map = generate_map(width, height)
    session = await create_minigame_session(user_id)
    steps = 0
    while any(get_all_lights_stats(game_map)):
        image = draw(game_map)
        p = UniMessage().image(raw=image).text(await lang.text("tol.msg", user_id, steps))
        msg = await prompt(await p.export())
        if msg is None:
            continue
        string = msg.extract_plain_text()
        if string[0] == "q":
            await session.quit()
        if re.match(f"^([1-{width}] [1-{height}])$", string) is None:
            await lang.send("tol.wrong_input", user_id)
            continue
        m = string.split(" ")
        game_map = change_light_stats(game_map, int(m[0]) - 1, int(m[1]) - 1)
        steps += 1
    time = await session.finish()
    points = await session.add_points(int((width * height * 21600) / ((1 + steps - math.sqrt(width * height)) * math.sqrt(time))))
    await lang.finish("tol.success", user_id, steps, points)
