import asyncio
import json
import traceback

import aiofiles
from nonebot import get_driver, logger
from nonebot.compat import type_validate_python
from nonebot_plugin_localstore import get_cache_dir

from .config import config
from .image import get_new_image
from .model import ImageData
from .types import ImageWithData

cache_dir = get_cache_dir("nonebot_plugin_larksetu")


async def get_cache_data() -> list[ImageData]:
    if not (p := cache_dir.joinpath("cache.json")).exists():
        return []
    try:
        async with aiofiles.open(p, encoding="utf-8") as f:
            return [type_validate_python(ImageData, data) for data in json.loads(await f.read())]
    except Exception:
        logger.warning(f"读取缓存信息失败: {traceback.format_exc}")
    return []


async def save_cache_data(data: list[ImageData]) -> None:
    p = cache_dir.joinpath("cache.json")
    async with aiofiles.open(p, "w", encoding="utf-8") as f:
        await f.write(json.dumps([image.dict() for image in data]))


async def create_image_cache() -> None:
    image = await get_new_image()
    async with aiofiles.open(
        cache_dir.joinpath(f"{image['data'].pid}_{image['data'].p}.{image['data'].ext}"), "wb"
    ) as f:
        await f.write(image["image"])
    cache_data = await get_cache_data()
    cache_data.append(image["data"])
    await save_cache_data(cache_data)


async def create_cache() -> bool:
    try:
        await create_image_cache()
        return True
    except Exception:
        logger.warning(f"更新 setu 缓存失败: {traceback.format_exc()}")
    return False


async def update_cache() -> None:
    logger.info("5s 后开始更新 setu 缓存")
    await asyncio.sleep(5)
    logger.info("开始更新 setu 缓存 ...")
    cache = await get_cache_data()
    for i in range(config.setu_cache_count - len(cache)):
        while not await create_cache():
            await asyncio.sleep(1)
    logger.success("setu 缓存更新完成！")


@get_driver().on_startup
async def _() -> None:
    asyncio.create_task(update_cache())


async def get_cached_img(data: ImageData) -> bytes:
    async with aiofiles.open(cache_dir.joinpath(f"{data.pid}_{data.p}.{data.ext}"), "rb") as f:
        image = await f.read()
    cache_dir.joinpath(f"{data.pid}_{data.p}.{data.ext}").unlink()
    return image


async def get_image() -> ImageWithData:
    asyncio.create_task(update_cache())
    cache_data = await get_cache_data()
    if not cache_data:
        return await get_new_image()
    data = cache_data.pop(0)
    await save_cache_data(cache_data)
    try:
        image = await get_cached_img(data)
    except Exception:
        logger.error(f"获取缓存图片失败: {traceback.format_exc()}")
        return await get_new_image()
    return {"data": data, "image": image}
