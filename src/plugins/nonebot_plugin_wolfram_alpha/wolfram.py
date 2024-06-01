import urllib.parse

import httpx

from .config import config
from .exceptions import ApiError

url_calc = "http://api.wolframalpha.com/v1/simple?appid={1}&i={0}&units=metric"


async def get_calc(question: str):
    url = url_calc.format(urllib.parse.quote(question), config.wolfram_api_key)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise ApiError()
    return response.read()
