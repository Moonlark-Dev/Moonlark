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
from nonebot.plugin.on import on_command
from nonebot.matcher import Matcher
from nonebot_plugin_larkutils import get_user_id
from .base import Scheduler, ControllableTeam, Team
from .characters import Delta
from .monomers import TestBot

test = on_command("fight-test")


@test.handle()
async def _(matcher: Matcher, user_id: str = get_user_id()) -> None:
    scheduler = Scheduler()
    player_team = ControllableTeam(scheduler, matcher, user_id)
    enemy_team = Team(scheduler, "B")
    Delta(
        player_team,
        {
            "experience": 0,
            "current_hp": 902,
            "fav": 0.0,
            "buff": [],
            "weapon": {"experience": 0, "damage_level": 0, "talent_level": {}},
            "equipment": [],
            "talent_level": {},
        },
    )
    TestBot(enemy_team)
    TestBot(enemy_team)
    await scheduler.setup()
    await scheduler.loop()
