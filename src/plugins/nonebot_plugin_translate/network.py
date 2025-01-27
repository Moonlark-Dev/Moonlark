import traceback
import httpx
from nonebot import logger
from .lang import lang
from nonebot.compat import type_validate_json
from .config import config
from pydantic import BaseModel


class TranslateResponse(BaseModel):
    alternatives: list[str]
    code: int
    data: str

async def post_translate_api(text: str, source_lang: str, target_lang: str) -> TranslateResponse:
    async with httpx.AsyncClient(base_url=config.translate_deeplx_url) as client:
        response = await client.post("/translate", json={
            "text": text,
            "source_lang": source_lang,
            "target_lang": target_lang
        })
    return type_validate_json(TranslateResponse, response.text)

async def translate(text: str, source_lang: str, target_lang: str, user_id: str) -> TranslateResponse:
    try:
        return await post_translate_api(text, source_lang, target_lang)
    except Exception as e:
        logger.error(f"翻译失败: {traceback.format_exc()}")
        await lang.finish("network.failed", user_id, e)
