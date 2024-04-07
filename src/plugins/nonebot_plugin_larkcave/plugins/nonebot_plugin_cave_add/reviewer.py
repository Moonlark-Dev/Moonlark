from typing import Optional
from nonebot_plugin_alconna import Image
from ....nonebot_plugin_larkutils import review_image, review_text


async def review_cave(content: list[Image | str]) -> Optional[str]:
    text = ""
    for segment in content:
        if isinstance(segment, str):
            text += f"{segment}"
        else:
            if (result := await review_image(segment.raw_bytes))["compliance"]:
                return result["message"]
    if (result := await review_text(text))["compliance"]:
        return result["message"]