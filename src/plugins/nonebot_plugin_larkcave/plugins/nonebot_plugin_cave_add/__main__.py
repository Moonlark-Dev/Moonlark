from typing import Union, cast
from nonebot_plugin_alconna import Arparma, Image, MultiVar, Text
from ...model import CaveData
from nonebot_plugin_orm import async_scoped_session
from ...__main__ import cave
from ....nonebot_plugin_larkutils import get_user_id
from ...lang import lang
from .encoder import encode_image, encode_text
from .reviewer import review_cave


async def get_cave_id() -> int:
    return 1    # TODO


@cave.assign("content")
async def _(session: async_scoped_session, result: Arparma, user_id: str = get_user_id) -> None:
    try:
        content = cast(list[Image | str], list(result.subcommands["add"].args["content"]))
    except KeyError:
        await lang.finish("add.empty", user_id)
        return
    if (message := await review_cave(content)):
        await lang.finish("add.review_fail", user_id, message)
    cave_id = await get_cave_id()
    content = " ".join([
        ((await encode_text(seg)) if isinstance(seg, str) else (await encode_image(cave_id, seg, session))) for seg in content
    ])
    # TODO

