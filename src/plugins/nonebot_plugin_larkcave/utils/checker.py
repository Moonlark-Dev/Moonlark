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

from ..exceptions import ReviewFailed, DuplicateCave, EmptyImage
from nonebot_plugin_alconna import Image, Text, UniMessage, image_fetch
from nonebot_plugin_larkutils import review_image, review_text
from nonebot.typing import T_State
from .similarity import check_text_content, check_image
from nonebot_plugin_orm import async_scoped_session
from nonebot.adapters import Event, Bot


def _flatten_content(content: list[Image | Text]) -> list[Image | Text]:
    """展开嵌套的 UniMessage 对象"""
    result: list[Image | Text] = []
    for seg in content:
        if isinstance(seg, UniMessage):
            result.extend(seg)
        else:
            result.append(seg)
    return result


async def check_cave(
    content: list[Image | Text], event: Event, bot: Bot, state: T_State, session: async_scoped_session
) -> None:
    content = _flatten_content(content)
    text = ""
    for segment in content:
        if isinstance(segment, Text):
            text += f"{segment.text}"
        else:
            _img = await image_fetch(event, bot, state, segment)
            if not isinstance(_img, bytes):
                raise EmptyImage
            image = _img
            data = await check_image(image, session, segment.name)
            if data["passed"] == False:
                raise DuplicateCave(data["similar_cave"], data["similarity"])
            elif not (result := await review_image(image))["compliance"]:
                raise ReviewFailed(str(result["message"]))
    data = await check_text_content(text, session)
    if data["passed"] == False:
        raise DuplicateCave(data["similar_cave"], data["similarity"])
    if text and not (result := await review_text(text))["compliance"]:
        raise ReviewFailed(str(result["message"]))
