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
from enum import Enum
from typing import Any, TypedDict, Literal, TYPE_CHECKING, Optional


if TYPE_CHECKING:
    from .base.monomer import Monomer
    from .base.equipment import Equipment


class AttackTypes(Enum):
    physical = 0
    wind = 1
    fire = 2
    electricity = 3
    ice = 4
    me = 5
    real = 6
    null = 7


class HarmData(TypedDict):
    target: "Monomer"
    harm_value: int
    harm_type: AttackTypes
    harm_missed: bool


class AttackEvent(TypedDict):
    type: Literal["harm.single"]
    origin: "Monomer"
    harms: list[HarmData]


class MessageActionEvent(TypedDict):
    type: Literal["normal"]
    message: str


class SkillInfo(TypedDict):
    name: str
    monomer: "Monomer"
    cost: int
    charge: bool
    instant: bool
    target_type: Literal["self", "enemy", "none"]


ACTION_EVENT = MessageActionEvent | AttackEvent


class BuffTypes(Enum):
    # buff_id, is_gain, keep
    pass


class BuffData(TypedDict):
    buff_type: BuffTypes
    remain_rounds: int
    data: dict[Any, Any]


class WeaponData(TypedDict):
    experience: int
    damage_level: int
    talent_level: dict[str, int]


class CharacterData(TypedDict):
    experience: int
    current_hp: int
    fav: float
    buff: list["BuffData"]
    weapon: WeaponData
    equipment: list["Equipment"]
    talent_level: dict[str, int]


class CurrentLevel(TypedDict):
    level: int
    current_exp: int
    exp_to_next: int
    progress: float
