from .config import config
from nonebot.log import logger
import re
from nonebot.adapters import Bot, Event
import math
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput
from nonebot_plugin_larkutils import LatestEvent, get_user_id
from .utils.generator import generate_map, change_light_stats
from .utils.image import draw
from nonebot_plugin_minigame_api import create_minigame_session

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
async def _(bot: Bot, event: Event, width: int, height: int, user_id: str = get_user_id()) -> None:
    if not (1 <= width <= 9 and 1 <= height <= 9):
        await lang.finish("tol.size_error", user_id)
    game_map = generate_map(width, height)
    session = await create_minigame_session(user_id, "tol")
    # 连续输入时始终回复用户最新消息，避免 QQ 官方被动回复次数超限
    tracker = LatestEvent(event, bot)
    steps = 0
    while any(get_all_lights_stats(game_map)):
        image = draw(game_map)
        waiter = WaitUserInput(
            UniMessage().image(raw=image).text(await lang.text("tol.msg", user_id, steps)),
            user_id,
            event=tracker.event,
        )
        try:
            await waiter.wait(timeout=config.tol_input_timeout, auto_finish=False)
        except TimeoutError:
            await session.quit(event=tracker.event, bot=bot)
        tracker.update(waiter.get_event())
        string = waiter.get()
        if not string:
            continue
        if string[0] == "q":
            await session.quit(event=tracker.event, bot=bot)
        if re.match(f"^([1-{width}] [1-{height}])$", string) is None:
            await tracker.send(await lang.text("tol.wrong_input", user_id), at_sender=True)
            continue
        m = string.split(" ")
        game_map = change_light_stats(game_map, int(m[0]) - 1, int(m[1]) - 1)
        steps += 1
    time, points = await session.finish(round((width * height * 21600) / ((1 + steps - math.sqrt(width * height)))))
    await tracker.send(await lang.text("tol.success", user_id, steps, points), at_sender=True)
    await matcher.finish()
