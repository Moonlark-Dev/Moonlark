import time
import uuid
from ...models import ImageData
import aiofiles
import zlib
from ...decoder import data_dir
from nonebot_plugin_orm import async_scoped_session


async def encode_text(text: str) -> str:
    return text.replace("[", "&#91;").replace("]", "&#93;")


async def encode_image(cave_id: int, name: str, data: bytes, session: async_scoped_session) -> str:
    image_id = time.time()
    file_id = uuid.uuid4().hex
    session.add(ImageData(id=image_id, file_id=file_id, data=data, name=name, belong=cave_id))
    async with aiofiles.open(data_dir.joinpath(file_id), "wb") as f:
        await f.write(zlib.compress(data))
    await session.commit()
    return f"[[Img:{image_id}]]]"
