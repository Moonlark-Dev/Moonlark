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

from .sudoku import (generate_new, get_problem, get_current, get_answer, change, erase, hint,  reset, undo, redo, 
                    able_to_change, able_to_undo, able_to_redo, view_problem, view_current, view_answer, conflict)
    

sudoku = on_alconna(
    Alconna(
        "sudoku", 
        Subcommand("new", Args["num_holes", int]),
        Subcommand("change", Args["y", int], Args["x", int], Args["value", int]),
        Subcommand("erase", Args["y", int], Args["x", int]),
        Subcommand("hint"),
        Subcommand("reset"),
        Subcommand("answer"),
        Subcommand("undo"),
        Subcommand("redo"),
    )
)
lang=LangHelper()
patch_matcher(sudoku)

def coordinate_valid(x: int, y: int):
    return 1<=x and x<=9 and 1<=y and y<=9

def number_valid(value: int):
    return 1<=value and value<=9

@creator("sudoku.html.jinja")
async def render(content: dict, user_id: str = get_user_id()):
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
    else:
        generate_new(num_holes)
        image=await render(get_problem(),user_id)
        await lang.send("new.generated",user_id)
        view_problem()
        await UniMessage().image(raw=image).send(reply_to=True)

@sudoku.assign("change")
async def _(y: int, x: int, value: int, user_id: str = get_user_id()):
    if not coordinate_valid(x, y):
        await lang.finish("change.position-invalid",user_id)
    elif not number_valid(value):
        await lang.finish("change.number-invalid",user_id)
    elif not able_to_change(x, y):
        await lang.finish("change.changed-origin",user_id)
    elif conflict(x, y, value):
        await lang.finish("change.conflict",user_id)
    else:
        change(x, y, value)
        image=await render(get_current(),user_id)
        await lang.send("change.success",user_id)
        view_current()
        await UniMessage().image(raw=image).send(reply_to=True)

@sudoku.assign("erase")
async def _(y: int, x: int, user_id: str = get_user_id()):
    if not coordinate_valid(x, y):
        await lang.finish("erase.position-invalid",user_id)
    elif not able_to_change(x, y):
        await lang.finish("erase.changed-origin",user_id)
    else:
        erase(x, y)
        image=await render(get_current(),user_id)
        await lang.send("erase.success",user_id)
        view_current()
        await UniMessage().image(raw=image).send(reply_to=True)

@sudoku.assign("hint")
async def _(user_id: str = get_user_id()):
    hint()
    image=await render(get_current(),user_id)
    await lang.send("hint.success",user_id)
    view_current()
    await UniMessage().image(raw=image).send(reply_to=True)

@sudoku.assign("reset")
async def _(user_id: str = get_user_id()):
    reset()
    image=await render(get_current(),user_id)
    await lang.send("reset.resets",user_id)
    view_current()
    await UniMessage().image(raw=image).send(reply_to=True)
    
@sudoku.assign("answer")
async def _(user_id: str = get_user_id()):
    image=await render(get_answer(),user_id)
    await lang.send("answer.answer-showed",user_id)
    view_answer()
    await UniMessage().image(raw=image).send(reply_to=True)


@sudoku.assign("undo")
async def _(user_id: str = get_user_id()):
    if not able_to_undo():
        await lang.finish("undo.no-more",user_id)
    else:
        undo()
        image=await render(get_current(),user_id)
        await lang.send("undo.success",user_id)
        view_current()
        await UniMessage().image(raw=image).send(reply_to=True)

@sudoku.assign("redo")
async def _(user_id: str = get_user_id()):
    if not able_to_redo():
        await lang.finish("redo.no-more",user_id)
    else:
        redo()
        image=await render(get_current(),user_id)
        await lang.send("redo.success",user_id)
        view_current()
        await UniMessage().image(raw=image).send(reply_to=True)
    
