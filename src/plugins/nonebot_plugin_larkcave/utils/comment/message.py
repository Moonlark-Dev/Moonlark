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

from typing import Optional
from ...types import CaveMessage
from ...config import config

cave_messages: list[CaveMessage] = []


def get_cave_by_message_id(message_id: str) -> Optional[int]:
    for message in cave_messages:
        if message["message_id"] == message_id:
            return message["cave_id"]
    return None


def add_cave_message(cave_id: int, message_id: str) -> None:
    global cave_messages
    cave_messages.append({"cave_id": cave_id, "message_id": message_id})
    cave_messages = cave_messages[-config.cave_message_list_length :]
    # print(cave_messages)
