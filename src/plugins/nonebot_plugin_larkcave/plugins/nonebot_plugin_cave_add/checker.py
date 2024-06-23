from typing import Optional
from .exception import EmptyImage, ReviewFailed, DuplicateCave
from nonebot_plugin_alconna import Image, Text, image_fetch
from ....nonebot_plugin_larkutils import review_image, review_text
from nonebot.typing import T_State
from ..nonebot_plugin_cave_similarity_check import check_text_content, check_image
from nonebot_plugin_orm import async_scoped_session
from nonebot.adapters import Event, Bot


async def check_cave(
    content: list[Image | Text], event: Event, bot: Bot, state: T_State, session: async_scoped_session
) -> None:
    text = ""
    for segment in content:
        if isinstance(segment, Text):
            text += f"{segment.text}"
        else:
            _img = await image_fetch(event, bot, state, segment)
            image = _img.__bytes__() if hasattr(_img, "__bytes__") else b""
            if not image:
                raise EmptyImage
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
