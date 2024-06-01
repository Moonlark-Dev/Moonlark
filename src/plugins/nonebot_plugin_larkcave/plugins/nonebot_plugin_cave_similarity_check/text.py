import re
from typing import Any, AsyncGenerator

from .exception import ImageOnlyCave
from .config import config
from .types import CheckResult
from ...models import CaveData
from nonebot_plugin_orm import async_scoped_session
import difflib
from sqlalchemy import select

async def get_public_cave_list(session: async_scoped_session) -> AsyncGenerator[CaveData, None]:
    cave_list = (await session.scalars(select(CaveData.id))).all()
    for cave_id in cave_list:
        yield await session.get_one(CaveData, {"id": cave_id})

def parse_text(text: str) -> str:
    result = re.search(r"\[\[Img:\d+\.\d+\]\]\]", text)
    if result:
        return parse_text(text.replace(result.group(0), ""))
    elif not text:
        raise ImageOnlyCave
    else:
        return text

async def get_similarity(posting: str, origin: str) -> float:
    return difflib.SequenceMatcher(
        None,
        origin,
        posting
    ).ratio()

async def get_cave_similarity(posting: str, cave: CaveData) -> float:
    try:
        return await get_similarity(
            posting,
            parse_text(cave.content)
        )
    except ImageOnlyCave:
        return 0

async def compare_cave_content(posting: str, cave: CaveData) -> CheckResult:
    if (similarity := await get_cave_similarity(posting, cave)) >= config.cave_maximum_similarity:
        return {
            "passed": False,
            "similar_cave": cave,
            "similarity": similarity
        }
    else:
        return {"passed": True}

async def check_text_content(posting: str, session: async_scoped_session) -> CheckResult:
    try:
        content = parse_text(posting)
    except ImageOnlyCave:
        return {"passed": True}
    async for cave in get_public_cave_list(session):
        if not (result := await compare_cave_content(content, cave))["passed"]:
            return result
    return {"passed": True}
    


