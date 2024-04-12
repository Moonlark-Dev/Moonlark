import base64
import time
import traceback
import aiofiles
from nonebot.log import logger
import httpx
from .types import ReviewResult
from pathlib import Path
from nonebot_plugin_localstore import get_cache_dir
import json

plugin_cache_dir: Path = get_cache_dir("nonebot_plugin_preview")
api_key = ""
secret_key = ""

async def get_access_token(force_update=False):
    try:
        async with aiofiles.open(plugin_cache_dir.joinpath("baiduAPI.json"), encoding="utf-8") as f:
            data = json.loads(await f.read())
        if not (force_update or data["expires_in"] < int(time.time())):
            return data["access_token"]
    except FileNotFoundError:
        pass
    url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=headers
        )
    odata = response.json()
    access_token = odata['access_token']
    expires_in = odata['expires_in']
    async with aiofiles.open(plugin_cache_dir.joinpath("baiduAPI.json"), "w", encoding="utf-8") as f:
        await f.write(json.dumps({
            "access_token": access_token,
            "expires_in": int(time.time()-30)+expires_in
        }))
    return access_token


def get_review_result(data: dict) -> ReviewResult:
    logger.debug(data)
    try:
        result: ReviewResult = {
            "compliance": data["conclusion"] in ["合规", "疑似"],
            "conclusion": data["conclusion"],
            "message": data.get("msg")
        }
        if not result["compliance"]:
            logger.warning(f"对象审核不通过: {data}")
    except KeyError:
        result: ReviewResult = {
            "compliance": False,
            "conclusion": "出错",
            "message": data.get("error_msg")
        }
        logger.warning(f"对象审核失败: {traceback.format_exc()}")
    logger.debug(str(result))
    return result

async def review_image(image: bytes) -> ReviewResult:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://aip.baidubce.com/rest/2.0/solution/v1/img_censor/v2/user_defined?access_token={await get_access_token()}",
            data={
                "image": base64.b64encode(image).decode()
            },
            headers={
                'content-type': 'application/x-www-form-urlencoded'
            }
        )
    data = response.json()
    data["msg"] = data["data"][0]["msg"] if data.get("data") else None
    return get_review_result(data)

async def review_text(text: str) -> ReviewResult:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://aip.baidubce.com/rest/2.0/solution/v1/text_censor/v2/user_defined?access_token={await get_access_token()}",
            data={
                "text": text
            },
            headers={
                'content-type': 'application/x-www-form-urlencoded'
            }
        )
    return get_review_result(response.json())


