import difflib 
from .config import config
from ..nonebot_plugin_larkutils import get_user_id
from ..nonebot_plugin_larklang import LangHelper
from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
import json
from typing import AsyncGenerator, TypedDict, Optional
import aiofiles
from pathlib import Path


def compare_string(target: str, origin: str) -> float:
    diffs = [0.0]
    for i in range(max(len(origin) - len(target), 1)):
         diffs.append(difflib.SequenceMatcher(None, target, origin[i:len(target) + i]).ratio())
    return max(*diffs)


class ChunkData(TypedDict):
     id: str
     book: str
     author: str
     type: str
     source: str
     date: str
     chunk: str
     window: str
     method: str


DATA_FILE_LIST = [
    "LuXunWorks.json_1.json",
    "LuXunWorks.json_2.json",
    "LuXunWorks.json_3.json",
    "LuXunWorks.json_4.json",
    "LuXunWorks.json_5.json",
    "LuXunWorks.json_6.json",
    "LuXunWorks.json_7.json"
]

async def get_works() -> AsyncGenerator[ChunkData, None]:
     for file in DATA_FILE_LIST:
          path = Path(__file__).parent / "data" / file
          async with aiofiles.open(path.as_posix(), encoding="utf-8") as f:
               chunks = json.loads(await f.read())
          _cache = None
          for chunk in chunks:
               if chunk["window"] != _cache:
                    _cache = chunk["window"]
                    yield chunk


async def match(query: str) -> tuple[float, Optional[ChunkData]]:
    _cache = (config.luxun_min_diff, None)
    async for chunk in get_works():
        if (diff := compare_string(query, chunk["window"])) >= _cache[0]:
            _cache = (diff, chunk)
    return _cache


lang = LangHelper()

@on_command("luxun-said").handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    if not (text := message.extract_plain_text()):
         await lang.finish("empty", user_id)
    result = await match(text)
    if result[1] is None:
         await lang.finish("result.failed", user_id)
    await lang.finish("result.found", user_id, round(result[0]*100), result[1]["window"], result[1]["book"])





