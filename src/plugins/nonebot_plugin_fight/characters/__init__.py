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
from typing import Optional

from .delta import Delta
from .moonlark import Moonlark

from ..base import ControllableTeam, Character
from ..models import Character as CharacterModel
from ..types import CharacterData

CHARACTERS: list[type[Character]] = [Delta, Moonlark]

async def get_character_by_data(team: ControllableTeam, data: CharacterModel) -> Optional[Character]:
    data_dict: CharacterData = {
        "experience": data.experience,
        "current_hp": 1145141919810,        # will be set later
        "fav": data.fav,
        "equipment": [],
        "talent_level": json.loads(data.talent_level),
        "buff": [],
        "weapon": {
            "experience": data.weapon_experience,
            "damage_level": data.weapon_damage
        }
    }
    for character in CHARACTERS:
        if character.get_character_id()[0] == data.character_type:
            target = character
            break
    else:
        return None
    c = target(team, data_dict)
    hp = c.get_max_hp() * (data.hp_percent / 100)
    c.health = hp
    return c
