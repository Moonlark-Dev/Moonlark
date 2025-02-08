import aiofiles
from pathlib import Path
import json
import random


async def get_dictionary(length: int) -> dict[str, str]:
    async with aiofiles.open(Path(__file__).parent.joinpath("EnWords.json"), encoding="utf-8") as f:
        data: dict[str, dict[str, str]] = json.loads(await f.read())
    return data[str(length)]


async def get_word_randomly(length: int) -> tuple[str, str]:
    data = await get_dictionary(length)
    return random.choice(list(data.items()))


async def is_valid_word(word: str) -> bool:
    data = await get_dictionary(len(word))
    return word in data
