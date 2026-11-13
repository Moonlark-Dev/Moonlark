#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from nonebot import on_command
from nonebot.adapters import Bot, Event

from .config import config
from .map2048 import Map2048
from nonebot_plugin_finding_the_trail.exceptions import Quited
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import LatestEvent, get_user_id
from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput
from nonebot_plugin_finding_the_trail.utils.enums.directions import Directions
from nonebot_plugin_minigame_api import create_minigame_session
from nonebot_plugin_alconna import UniMessage
from io import BytesIO

lang = LangHelper()
cmd = on_command("2048")
patch_matcher(cmd)


async def get_input(game_map: Map2048, user_id: str, tracker: LatestEvent) -> Directions:
    while True:
        buffer = BytesIO()
        game_map.draw().save(buffer, format="PNG")
        waiter = WaitUserInput(
            UniMessage()
            .image(raw=buffer.getvalue())
            .text(await lang.text("game.prompt", user_id, game_map.get_score())),
            user_id,
            checker=lambda text: text.lower() in ["w", "s", "a", "d", "q"],
            event=tracker.event,
        )
        try:
            await waiter.wait(timeout=config.mg2048_input_timeout, auto_finish=False)
        except TimeoutError:
            raise Quited from None
        tracker.update(waiter.get_event())
        text = waiter.get().lower()
        if text == "q":
            raise Quited
        return {"w": Directions.UP, "s": Directions.DOWN, "a": Directions.LEFT, "d": Directions.RIGHT}[text]


@cmd.handle()
async def _(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    session = await create_minigame_session(user_id, "2048")
    game_map = Map2048()
    # 连续输入时始终回复用户最新消息，避免 QQ 官方被动回复次数超限
    tracker = LatestEvent(event, bot)
    while True:
        try:
            game_map.put_number()
        except ValueError:
            break
        try:
            direction = await get_input(game_map, user_id, tracker)
        except Quited:
            break
        if not game_map.move(direction):
            await tracker.send(await lang.text("game.cannot_move", user_id), at_sender=True)
    score = game_map.get_score()
    t, p = await session.finish(score, 0.75)
    await tracker.send(await lang.text("game.failed", user_id, t, p, score), at_sender=True)
    await cmd.finish()
