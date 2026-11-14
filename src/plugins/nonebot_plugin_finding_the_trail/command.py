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

import os
import struct
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_larkuser.utils.waiter2 import Waiter
from nonebot_plugin_larkutils import LatestEvent, get_user_id
from nonebot_plugin_schedule.utils import complete_schedule
from nonebot_plugin_minigame_api import create_minigame_session
from .config import config
from .exceptions import Quited, CannotMove
from .utils.fttmap import FttMap
from .utils.enums import Directions, Blocks
from .utils.string import get_command_list_string
from .utils.answer import AnswerGetter
from .utils.image.legend import generate_legend_image
from .__main__ import ftt, lang


async def get_block_info(user_id: str) -> tuple[dict[Blocks, str], dict[Blocks, str], str]:
    """获取方块名称和描述"""
    block_names = {
        Blocks.NULL: await lang.text("legend.null_block.name", user_id),
        Blocks.WALL: await lang.text("legend.wall.name", user_id),
        Blocks.START: await lang.text("legend.start.name", user_id),
        Blocks.END: await lang.text("legend.end.name", user_id),
        Blocks.PISTON: await lang.text("legend.piston.name", user_id),
        Blocks.SAND: await lang.text("legend.sand.name", user_id),
        Blocks.PORTAL: await lang.text("legend.portal.name", user_id),
        Blocks.COBWEB: await lang.text("legend.cobweb.name", user_id),
        Blocks.GOLD_PISTON: await lang.text("legend.gold_piston.name", user_id),
    }
    block_descs = {
        Blocks.NULL: await lang.text("legend.null_block.desc", user_id),
        Blocks.WALL: await lang.text("legend.wall.desc", user_id),
        Blocks.START: await lang.text("legend.start.desc", user_id),
        Blocks.END: await lang.text("legend.end.desc", user_id),
        Blocks.PISTON: await lang.text("legend.piston.desc", user_id),
        Blocks.SAND: await lang.text("legend.sand.desc", user_id),
        Blocks.PORTAL: await lang.text("legend.portal.desc", user_id),
        Blocks.COBWEB: await lang.text("legend.cobweb.desc", user_id),
        Blocks.GOLD_PISTON: await lang.text("legend.gold_piston.desc", user_id),
    }
    title = await lang.text("legend.title", user_id)
    return block_names, block_descs, title


async def is_user_continue(user_id: str, d_list: list[Directions], tracker: LatestEvent) -> bool:
    while True:
        waiter = Waiter(
            UniMessage(await lang.text("ftt.done", user_id, await get_command_list_string(d_list, user_id))),
            user_id,
            event=tracker.event,
        )
        try:
            await waiter.wait(timeout=config.ftt_input_timeout, auto_finish=False)
        except TimeoutError:
            raise Quited from None
        tracker.update(waiter.get_event())
        text = waiter.get(lambda message: message.extract_plain_text()).lower()
        if text == "ok":
            return True
        elif text == "clear":
            return False


@ftt.handle()
async def _(bot: Bot, event: Event, seed: str, user_id: str = get_user_id()) -> None:
    # 如果 seed 是 "help"，不处理，让 help 子命令处理器处理
    if seed in ["legend", "help"]:
        await get_legend(user_id)
        return
    map_seed = seed if seed != "-1" else str(struct.unpack("I", os.urandom(4))[0])
    ftt_map = FttMap(map_seed)
    points = ftt_map.difficulty["points"]
    session = await create_minigame_session(user_id, "ftt")
    # 连续输入过程中始终回复用户最新消息，避免 QQ 官方被动回复次数超限
    tracker = LatestEvent(event, bot)
    while points >= 2:
        getter = AnswerGetter(user_id, ftt_map, tracker)
        try:
            d_list = await getter.get_commands()
            if not await is_user_continue(user_id, d_list, tracker):
                continue
        except Quited:
            break
        try:
            result = ftt_map.test_answer(d_list)
        except CannotMove as e:
            if points / 2 >= 2:
                points /= 2
                await tracker.send(await lang.text("ftt.cannot_move", user_id, e.step_length + 1), at_sender=True)
                continue
            else:
                await tracker.send(await lang.text("ftt.cannot_move_end", user_id, e.step_length + 1), at_sender=True)
                break
        if points / 2 >= 2 and not result:
            points /= 2
            await tracker.send(await lang.text("ftt.failed", user_id), at_sender=True)
        elif not result:
            await tracker.send(await lang.text("ftt.big_failed", user_id), at_sender=True)
            break
        else:
            if seed != "-1":
                points = 5
            t, points = await session.finish(round(points * (ftt_map.step_length / 5)), 1.6)
            if ftt_map.difficulty_name != "easy":
                await complete_schedule(user_id, "ftt")
            await tracker.send(await lang.text("ftt.success", user_id, points, map_seed), at_sender=True)
            await ftt.finish()
    await session.quit(
        await lang.text("ftt.example", user_id, await get_command_list_string(ftt_map.answer, user_id), map_seed),
        event=tracker.event,
        bot=bot,
    )


async def get_legend(user_id: str = get_user_id()) -> None:
    """处理 ftt legend 命令，显示方块图例"""
    block_names, block_descs, title = await get_block_info(user_id)
    image_bytes = generate_legend_image(block_names, block_descs, title)
    await UniMessage().image(raw=image_bytes).send()
