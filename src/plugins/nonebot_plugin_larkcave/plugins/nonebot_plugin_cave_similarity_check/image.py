import asyncio
from typing import AsyncGenerator
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from imagededup.methods import PHash
from nonebot.log import logger

from .types import CheckResult
from ...model import CaveData, ImageData
import numpy as np

phasher = PHash()

# TODO 优化执行效率

def compare_images(image1: bytes, image2: ImageData, image1_name: str) -> float:
    encodings = {
        f'1_{image1_name}': phasher.encode_image(np.array(image1)),
        f'2_{image2.name}': phasher.encode_image(np.array(image2.data))
    }
    result = phasher.find_duplicates(encoding_map=encodings, scores=True)
    logger.debug(result)
    if not (images := result.get(f'1_{image1_name}')):
        return 0
    try:
        return images[0][0]
    except IndexError:
        return 0

async def compare_images_async(image1: bytes, image2: ImageData, image1_name: str) -> float:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, compare_images, image1, image2, image1_name)

async def get_image_list(session: async_scoped_session) -> AsyncGenerator[ImageData, None]:
    image_list = await session.scalars(select(ImageData.id))
    for image_id in image_list.all():
        yield await session.get_one(ImageData, {"id": image_id})

async def check_image(posting: bytes, session: async_scoped_session, name: str) -> CheckResult:
    async for image in get_image_list(session):
        if (score := await compare_images_async(posting, image, name)):
            return {
                "passed": False,
                "similar_cave": await session.get_one(CaveData, {"id": image.belong}),
                "similarity": score
            }
    return {"passed": True}