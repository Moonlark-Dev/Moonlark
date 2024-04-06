import httpx
from nonebot import logger
from .exception import NoImageInResponse
from .config import config
from .types import ImageWithData
from .model import LoliconResponse
from ..nonebot_plugin_larkutils import review_image

async def get_image_data() -> LoliconResponse:
    async with httpx.AsyncClient(proxy=config.setu_proxy) as client:
        response = await client.get("https://api.lolicon.app/setu/v2?r18=0")
    return LoliconResponse(**response.json())

async def download_image(url: str) -> bytes:
    logger.info(f"Downloading {url} ...")
    async with httpx.AsyncClient(proxy=config.setu_proxy) as client:
        return (await client.get(url)).read()

async def _review_image(image: bytes) -> bytes:
    if (await review_image(image))["compliance"]:
        return image
    raise NoImageInResponse()

async def get_new_image() -> ImageWithData:
    image_data = await get_image_data()
    if image_data.data:
        return {
            "data": image_data.data[0],
            "image": await _review_image(await download_image(image_data.data[0].urls.original))
        }
    raise NoImageInResponse()