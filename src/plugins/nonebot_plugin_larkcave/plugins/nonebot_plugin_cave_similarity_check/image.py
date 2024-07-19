import asyncio
import io
from typing import AsyncGenerator
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from PIL import UnidentifiedImageError
from .types import CheckResult
import numpy as np
from PIL import Image

from ...models import CaveData, ImageData, CaveImage
from ...decoder import get_image

# FROM https://github.com/xxtg666/XDbot2FTTsolver/blob/main/xdbot_ftt_solver.py#L23C5-L28C30
from skimage.metrics import structural_similarity as ssim


def compare_image(img1, img2):
    if img1.shape != img2.shape:
        return 0
    s = ssim(img1, img2, channel_axis=2, multichannel=True)
    return s


def compare_images(image1: bytes, image2: CaveImage, *_) -> float:
    try:  # NOTE 解决数据库内空白图片的问题
        img2 = np.array(Image.open(io.BytesIO(image2.data)))
    except UnidentifiedImageError:
        return 0
    return compare_image(np.array(Image.open(io.BytesIO(image1))), img2)


async def compare_images_async(image1: bytes, image2: CaveImage, image1_name: str) -> float:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, compare_images, image1, image2, image1_name)


async def get_image_list(session: async_scoped_session) -> AsyncGenerator[CaveImage, None]:
    image_list = await session.scalars(select(ImageData.id))
    for image_id in image_list.all():
        yield await get_image(str(image_id), session)


async def check_image(posting: bytes, session: async_scoped_session, name: str) -> CheckResult:
    async for image in get_image_list(session):
        if (score := await compare_images_async(posting, image, name)) >= 0.9:
            return {
                "passed": False,
                "similar_cave": await session.get_one(CaveData, {"id": image.belong}),
                "similarity": score,
            }
    return {"passed": True}
