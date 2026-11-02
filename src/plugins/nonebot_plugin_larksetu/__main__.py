import time
import traceback
from typing import Optional

from nonebot import logger
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from . import counter
from .cache import get_cached_image, get_image
from .config import config
from .types import ImageWithData

lang = LangHelper()
setu = on_alconna(
    Alconna("setu", Subcommand("rank")),
    skip_for_unmatch=False,
    # auto_send_output=True
)
# 查看缓存中的原图（签到卡片等场景会保留图片，用于按 ID 取回）
setu_g = on_alconna(
    Alconna("setu-g", Args["image_id", str]),
    skip_for_unmatch=False,
)
last_use = 0


async def _get_image() -> Optional[ImageWithData]:
    for _ in range(config.setu_retry_time):
        try:
            return await get_image()
        except Exception:
            logger.warning(f"获取图片失败: {traceback.format_exc()}")


async def _send_image(image: ImageWithData, user_id: str) -> None:
    await (
        UniMessage()
        .image(raw=image["image"], name=f"image.{image['data'].ext}")
        .text(await lang.text("setu.info", user_id, image["data"].title, image["data"].author, image["data"].pid))
        .send()
    )


@setu.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    global last_use
    if (remain_time := time.time() - last_use) <= config.setu_cd:
        await lang.finish("setu.cd", user_id, round(remain_time, 2))
    if not (image := await _get_image()):
        await lang.finish("setu.failed", user_id)
    await _send_image(image, user_id)
    await counter.add(user_id, session)
    last_use = time.time()
    await setu.finish()


@setu_g.assign("$main")
async def _setu_get_handler(image_id: str, user_id: str = get_user_id()) -> None:
    """从缓存取回原图并发送，不计入 setu 排行"""
    image = await get_cached_image(image_id)
    if image is None:
        await lang.finish("setu.expired", user_id)
    await _send_image(image, user_id)
    await setu_g.finish()
