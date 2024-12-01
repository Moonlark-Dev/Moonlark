from concurrent.futures import ProcessPoolExecutor
import difflib
import asyncio
from .config import config
from ..nonebot_plugin_larkutils import get_user_id
from ..nonebot_plugin_larklang import LangHelper
from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
import json
from typing import Generator, TypedDict, Optional
import aiofiles
from pathlib import Path

"""
def compare_string(target: str, origin: str) -> float:
    diffs = [0.0]
    for i in range(max(len(origin) - len(target), 1)):
        diffs.append(difflib.SequenceMatcher(None, target, origin[i : len(target) + i]).ratio())
    return max(*diffs)
"""

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
    "LuXunWorks.json_7.json",
]


def get_works_sync(file: str) -> Generator[ChunkData, None, None]:
     path = Path(__file__).parent / "data" / file
     with open(path.as_posix(), encoding="utf-8") as f:
          chunks = json.loads(f.read())
     for chunk in chunks:
          yield chunk


def match_sync(query: str, file: str) -> tuple[float, Optional[ChunkData]]:
    _cache = (config.luxun_min_diff, None)
    for chunk in get_works_sync(file):
        if (diff := difflib.SequenceMatcher(None, query, chunk["chunk"]).ratio()) >= _cache[0]:
            _cache = (diff, chunk)
    return _cache


lang = LangHelper()


@on_command("luxun-said").handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    if not (text := message.extract_plain_text()):
        await lang.finish("empty", user_id)
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        tasks = [loop.run_in_executor(executor, match_sync, text, file) for file in DATA_FILE_LIST]
        task_results = await asyncio.gather(*tasks)
    result = sorted(task_results, key=lambda x: x[0], reverse=True)[0]
    if result[1] is None:
        await lang.finish("result.failed", user_id)
    await lang.finish("result.found", user_id, round(result[0] * 100), result[1]["window"], result[1]["book"])
