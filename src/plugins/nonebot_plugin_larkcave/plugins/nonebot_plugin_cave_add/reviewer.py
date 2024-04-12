from typing import Optional, cast
from nonebot_plugin_alconna import Image, Text, image_fetch
from ....nonebot_plugin_larkutils import review_image, review_text
from nonebot.typing import T_State
from nonebot.adapters import Event, Bot

async def review_cave(content: list[Image | Text], event: Event, bot: Bot, state: T_State) -> Optional[str]:
    text = ""
    for segment in content:
        if isinstance(segment, Text):
            text += f"{segment.text}"
        else:
            image = await image_fetch(event, bot, state, segment)
            if not (result := await review_image(image.__bytes__()))["compliance"]:
                return result["message"]
    if (result := await review_text(text))["compliance"]:
        return result["message"]