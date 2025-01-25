#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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
from typing import Any, TypedDict, Literal, TYPE_CHECKING, Optional



if TYPE_CHECKING:
    from src.plugins.nonebot_plugin_fight.base.monomer import Monomer
    from src.plugins.nonebot_plugin_fight.base.equipment import Equipment
    from src.plugins.nonebot_plugin_fight.base.weapon import Weapon    


class AttackEvent(TypedDict):
    type: Literal["harm.single"]
    origin: "Monomer"
    target: "Monomer"
    harm_value: int
    harm_type: str
    harm_missed: bool


class MessageActionEvent(TypedDict):
    type: Literal["normal"]
    message: str


class SkillInfo(TypedDict):
    name: str
    monomer: "Monomer"
    occupy_round: bool
    cost: int
    instant: bool
    target_type: Literal["self", "enemy", "none"]


class ActionCommand(TypedDict):
    skill_index: int
    target: Optional["Monomer"]
    skill_info: SkillInfo


ACTION_EVENT = MessageActionEvent | AttackEvent


class CharacterData(TypedDict):
    experience: int
    current_hp: int
    fav: float
    buff: list[dict[str, Any]]
    weapon: "Weapon"
    equipment: "Equipment"
    talent_level: dict[str, int]
