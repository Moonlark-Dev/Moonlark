import time
from nonebot_plugin_alconna import Image, Text
from ...model import ImageData
from nonebot_plugin_orm import async_scoped_session

async def encode_text(text: str) -> str:
    return text.replace("[", "&#91;").replace("]", "&#93;")

async def encode_image(cave_id: int, image: Image, session: async_scoped_session) -> str:
    image_id = time.time()
    session.add(ImageData(
        id=image_id,
        data=image.raw_bytes,
        name=image.name,
        belong=cave_id
    ))
    await session.commit()
    return f"[[Img:{image_id}]]]"
