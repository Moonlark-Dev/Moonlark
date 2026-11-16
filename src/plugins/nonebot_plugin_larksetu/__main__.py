import time
import traceback
from typing import Optional

from nonebot import logger
from nonebot.exception import ActionFailed
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
# QQ 官方机器人内容安全审核不通过（图片被判违规）时返回的错误码
CONTENT_VIOLATION_CODE = 40034006


def _is_content_violation(error: Exception) -> bool:
    """判断发送失败是否由平台内容审核拦截引起

    只有 QQ 官方适配器的 ActionFailed 才带 ``code``，其它适配器（OneBot V11/V12 等）
    没有该字段，一律按普通发送失败处理。
    """
    return isinstance(error, ActionFailed) and str(getattr(error, "code", "")) == str(CONTENT_VIOLATION_CODE)


async def _get_image() -> Optional[ImageWithData]:
    for _ in range(config.setu_retry_time):
        try:
            return await get_image()
        except Exception:
            logger.warning(f"获取图片失败: {traceback.format_exc()}")


async def _send_image(image: ImageWithData, user_id: str) -> bool:
    """发送图片与元数据，被内容审核拦截时返回 ``False`` 由调用方提示用户"""
    try:
        await (
            UniMessage()
            .image(raw=image["image"], name=f"image.{image['data'].ext}")
            .text(await lang.text("setu.info", user_id, image["data"].title, image["data"].author, image["data"].pid))
            .send()
        )
    except ActionFailed as e:
        if not _is_content_violation(e):
            raise
        logger.warning(f"setu 图片被内容安全审核拦截: {e!r}")
        return False
    return True


@setu.assign("$main")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    global last_use
    if (remain_time := time.time() - last_use) <= config.setu_cd:
        await lang.finish("setu.cd", user_id, round(remain_time, 2))
    if not (image := await _get_image()):
        await lang.finish("setu.failed", user_id)
    if not await _send_image(image, user_id):
        # 图片已被平台拦截：不消耗冷却、不计入排行，用户可以立刻重试
        await lang.finish("setu.blocked", user_id)
    await counter.add(user_id, session)
    last_use = time.time()
    await setu.finish()


@setu_g.assign("$main")
async def _setu_get_handler(image_id: str, user_id: str = get_user_id()) -> None:
    """从缓存取回原图并发送，不计入 setu 排行"""
    image = await get_cached_image(image_id)
    if image is None:
        await lang.finish("setu.expired", user_id)
    if not await _send_image(image, user_id):
        await lang.finish("setu.blocked", user_id)
    await setu_g.finish()
