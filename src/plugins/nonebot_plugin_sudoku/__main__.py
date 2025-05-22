import asyncio
from unittest.util import sorted_list_difference
from nonebot_plugin_larklang.__main__ import load_languages
from pathlib import Path
import sys
from typing import Any, Optional, Literal

from nonebot import get_driver, logger
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Subcommand
from nonebot_plugin_alconna.uniseg import UniMessage

from nonebot_plugin_render.render import render_template
from nonebot_plugin_render.cache import creator

from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot.exception import FinishedException

from .sudoku import generate_new, get_problem, get_answer

sudoku = on_alconna(
    Alconna(
        "sudoku", 
        Subcommand("new",Args["num_holes",int,20]),
        Subcommand("fill", Args["x", int], Args["y", int], Args["value", int]),
        Subcommand("clear", Args["x",int], Args["y",int]),
        Subcommand("answer"),
        Subcommand("undo"),
        Subcommand("redo"),
    )
)
lang=LangHelper()
patch_matcher(sudoku)

operations=[]

@creator("sudoku.html.jinja")
async def render(content: dict, user_id: str = get_user_id()):
    logger.log("INFO", content)
    return await render_template(
        "sudoku.html.jinja",
        "",
        user_id,
        content,
        {},
        True
    )

@sudoku.assign("new")
async def _(num_holes: int, user_id: str = get_user_id()):
    if num_holes<=0 or num_holes>=81: 
        await lang.finish("new.number-invalid",user_id)
    generate_new(num_holes)
    image=await render(get_problem(),user_id)
    await lang.send("new.generated",user_id)
    await UniMessage().image(raw=image).send(reply_to=True)

@sudoku.assign("fill")
async def _(x: int, y: int, value: int, user_id: str = get_user_id()):
    # generate_new(num_holes)
    # image=await render(get_problem(),user_id)
    # await lang.send("sudoku.generated",user_id)
    # await UniMessage().image(raw=image).send(reply_to=True)
    pass

@sudoku.assign("clear")
async def _(x: int, y: int, user_id: str = get_user_id()):
    # generate_new(num_holes)
    # image=await render(get_problem(),user_id)
    # await lang.send("sudoku.generated",user_id)
    # await UniMessage().image(raw=image).send(reply_to=True)
    pass

@sudoku.assign("answer")
async def _(user_id: str = get_user_id()):
    image=await render(get_answer(),user_id)
    await lang.send("answer.answer-showed",user_id)
    await UniMessage().image(raw=image).send(reply_to=True)


@sudoku.assign("undo")
async def _(x: int, y: int, user_id: str = get_user_id()):
    # generate_new(num_holes)
    # image=await render(get_problem(),user_id)
    # await lang.send("sudoku.generated",user_id)
    # await UniMessage().image(raw=image).send(reply_to=True)
    pass

@sudoku.assign("redo")
async def _(x: int, y: int, user_id: str = get_user_id()):
    # generate_new(num_holes)
    # image=await render(get_problem(),user_id)
    # await lang.send("sudoku.generated",user_id)
    # await UniMessage().image(raw=image).send(reply_to=True)
    pass
    
