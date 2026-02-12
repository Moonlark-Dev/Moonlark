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
import json
from datetime import datetime
from typing import Optional

from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args, UniMessage
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkutils import get_user_id
from ..base import ControllableTeam, Scheduler
from ..characters import get_character_by_data
from ..consts import PLAYER_TEAM_CHARACTER_COUNT_LIMIT
from ..models import PlayerTeam, Character as CharacterData
from ..lang import lang

team_cmd = on_alconna(
    Alconna(
        "team",
        Subcommand("set", Args["pos", int], Args["character_index", int]),
        # Subcommand("fast-set", Args["characters", MultiVar(int)])
    )
)
patch_matcher(team_cmd)


@team_cmd.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    # characters = await session.scalars(select(CharacterData).where(CharacterData.user_id == user_id).order_by(CharacterData.character_id))
    team_result = await session.get(PlayerTeam, {"user_id": user_id})
    if team_result is None:
        await lang.finish("cmd.t.none", user_id)
    character_list = ""
    temp_scheduler = Scheduler(datetime.now())
    team = ControllableTeam(temp_scheduler, team_cmd, user_id)
    data = json.loads(team_result.character_list)
    print(data)
    for i in range(PLAYER_TEAM_CHARACTER_COUNT_LIMIT):
        index = i + 1
        character_id = data.get(str(index))
        if character_id is None:
            character_list += await lang.text("cmd.t.empty", user_id, index)
            continue
        character = await get_character_by_data(
            team, await session.get_one(CharacterData, {"character_id": character_id})
        )
        if character:
            character_list += await lang.text(
                "cmd.c.line",
                user_id,
                index,
                await character.get_name(user_id),
                character.get_level(True),
                round(character.get_hp_percent() * 100),
            )
    await lang.finish("cmd.t.title", user_id, character_list)


@team_cmd.assign("set")
async def _(session: async_scoped_session, pos: int, character_index: int, user_id: str = get_user_id()) -> None:
    if not 0 < pos <= PLAYER_TEAM_CHARACTER_COUNT_LIMIT:
        await lang.finish("cmd.t.wrong_pos", user_id)
    pos = str(pos)
    character = (
        await session.scalars(
            select(CharacterData).where(CharacterData.user_id == user_id).order_by(CharacterData.character_id)
        )
    ).all()[character_index - 1]
    team_result = await session.get(PlayerTeam, {"user_id": user_id})
    if team_result is None:
        team_result = PlayerTeam(user_id=user_id, character_list=json.dumps({pos: character.character_id}))
        session.add(team_result)
        await session.commit()
    else:
        data: dict[str, Optional[int]] = json.loads(team_result.character_list)
        for k in data:
            if data[k] == character.character_id:
                data[k] = None
        data[pos] = character.character_id
        team_result.character_list = json.dumps(data)
        await session.commit()
        await lang.finish("cmd.t.success", user_id)
