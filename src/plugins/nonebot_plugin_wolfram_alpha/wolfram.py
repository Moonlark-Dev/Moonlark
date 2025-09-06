import urllib.parse

import httpx

from .config import config
from .exceptions import ApiError

URL_SIMPLE = "https://api.wolframalpha.com/v1/simple?appid={1}&i={0}&units=metric"
URL_LLM_API = "https://www.wolframalpha.com/api/v1/llm-api?input={0}&appid={1}"

async def request_simple(question: str):
    url = URL_SIMPLE.format(urllib.parse.quote(question), config.wolfram_api_key)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise ApiError()
    return response.read()

async def request_llm_api(question: str) -> str:
    url = URL_LLM_API.format(urllib.parse.quote(question), config.wolfram_api_key)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise ApiError()
    return response.text


