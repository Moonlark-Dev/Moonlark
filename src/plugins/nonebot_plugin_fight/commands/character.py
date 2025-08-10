#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
from datetime import datetime

from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args, UniMessage
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template

from ..utils import level
from ..base import ControllableTeam, Scheduler
from ..characters import get_character_by_data
from ..models import Character as CharacterData
from ..lang import lang
from ..utils.initial_character import init_user_character

character_cmd = on_alconna(Alconna(
    "character",
    Subcommand("show", Args["index", int])
))
patch_matcher(character_cmd)


@character_cmd.handle()
async def _(user_id: str = get_user_id()) -> None:
    await init_user_character(user_id)

@character_cmd.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    result = await session.scalars(select(CharacterData).where(CharacterData.user_id == user_id).order_by(CharacterData.character_id))
    character_list = ""
    temp_scheduler = Scheduler(datetime.now())
    temp_team = ControllableTeam(temp_scheduler, character_cmd, user_id)
    index = 0
    for character_data in result:
        index += 1
        character = await get_character_by_data(temp_team, character_data)
        if character:
            character_list += await lang.text(
                "cmd.c.line",
                user_id,
                index,
                await character.get_name(user_id),
                character.get_level(True),
                round(character.get_hp_percent() * 100)
            )
    await lang.finish("cmd.c.main", user_id, character_list)


@character_cmd.assign("show")
async def _(session: async_scoped_session, index: int, user_id: str = get_user_id()) -> None:
    result = await session.scalars(select(CharacterData).where(CharacterData.user_id == user_id).order_by(CharacterData.character_id))
    temp_scheduler = Scheduler(datetime.now())
    temp_team = ControllableTeam(temp_scheduler, character_cmd, user_id)
    character = await get_character_by_data(temp_team, result.all()[index - 1])
    await character_cmd.finish(UniMessage().image(raw=await render_template(
        "fight_character.html.jinja",
        await lang.text("cmd.c.title", user_id, await character.get_name(user_id)),
        user_id,
        {
            "round": round,
            "c": {
                "name": await character.get_name(user_id),
                "greeting": None,
                "hp": character.get_hp(),
                "max_hp": character.get_max_hp(),
                "level": level.character.get_current_level(character.character_data["experience"]),
                "attack": character.get_attack_value(),
                "defuse": character.get_defuse(),
                "crit_rate": character.critical_strike[0],
                "crit_damage": character.critical_strike[1],
                "speed": character.speed,
                "max_power": character.final_skill_power[1],
                "weapon_lv": level.weapon.get_current_level(character.character_data["weapon"]["experience"]),
                "weapon": {
                    "damage": character.character_data["weapon"]["damage_level"],
                    "story": None
                }
            }
        }
    )))



