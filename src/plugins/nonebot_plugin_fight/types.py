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
from typing import TypedDict, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from src.plugins.nonebot_plugin_fight.base.monomer import Monomer


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


class FinalSkillPowered(TypedDict):
    type: Literal["me.final_skill.powered"]


ACTION_EVENT = MessageActionEvent | AttackEvent | FinalSkillPowered
