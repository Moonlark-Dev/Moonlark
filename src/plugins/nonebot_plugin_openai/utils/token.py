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

from nonebot_plugin_orm import get_session
from openai.types.chat.chat_completion import ChatCompletion
from nonebot_plugin_larkuser import get_user

from ..models import GptUser


async def is_user_useable(user_id: str) -> bool:
    return (await get_user(user_id)).is_registered()


def get_used_token(completion: ChatCompletion) -> int:
    if completion.usage is None:
        return 0
    return completion.usage.total_tokens


async def reduce_token(user_id: str, count: int) -> None:
    async with get_session() as session:
        if (user := await session.get(GptUser, user_id)) is not None:
            user.used_token += count
        else:
            user = GptUser(user_id=user_id, used_token=count)
        await session.merge(user)
        await session.commit()


async def reduce_completion_token(user_id: str, completion: ChatCompletion, multiple: float = 1.0) -> None:
    return await reduce_token(user_id, round(get_used_token(completion) * multiple))
