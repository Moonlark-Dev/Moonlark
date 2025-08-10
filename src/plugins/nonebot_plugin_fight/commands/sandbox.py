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
from datetime import datetime, timedelta

from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args, UniMessage
from nonebot_plugin_orm import async_scoped_session, get_session
from sqlalchemy import select

from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template
from ..consts import PLAYER_TEAM_CHARACTER_COUNT_LIMIT
from ..monsters import TargetBot

from ..utils import level
from ..base import ControllableTeam, Scheduler, Team
from ..characters import get_character_by_data
from ..models import Character as CharacterData, PlayerTeam
from ..lang import lang


sandbox = on_alconna(Alconna("sandbox", Args["monster_level", int, 1], Args["monster_count", int, 1]))

async def get_player_team(user_id: str, scheduler: Scheduler, matcher: Matcher, team_id: str = "A") -> ControllableTeam:
    async with get_session() as session:
        result = await session.get(PlayerTeam, user_id)
        if result is None:
            raise ValueError("user hasn't set team yet")
        team_data = json.loads(result.character_list)
    team = ControllableTeam(scheduler, matcher, user_id, team_id)
    for i in range(PLAYER_TEAM_CHARACTER_COUNT_LIMIT):
        if team_data.get(str(i)) is not None:
            await get_character_by_data(team, team_data[i])
    return team


@sandbox.handle()
async def _(monster_level: int, monster_count: int, user_id: str = get_user_id()) -> None:
    scheduler = Scheduler(datetime.now() + timedelta(minutes=3))
    try:
        player_team = await get_player_team(user_id, scheduler, sandbox)
    except ValueError:
        await lang.finish("no_team", user_id=user_id)
        return
    monster_team = Team(scheduler, "B")
    for i in range(monster_count):
        TargetBot(monster_team, monster_level)
    await scheduler.setup()
    win_team = await scheduler.loop()
    if win_team is player_team:
        fight_result = await lang.text("result.player_team_win", user_id=user_id)
    elif win_team is monster_team:
        fight_result = await lang.text("result.monster_win", user_id=user_id)
    else:
        fight_result = await lang.text("result.time_ran_out", user_id=user_id)
    await lang.finish("result.main", user_id, fight_result)



