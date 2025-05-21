import asyncio
from unittest.util import sorted_list_difference
from nonebot_plugin_larklang.__main__ import load_languages
from pathlib import Path
import sys
from typing import Any, Optional, Literal

from nonebot import get_driver
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Subcommand
from nonebot_plugin_alconna.uniseg import UniMessage

from nonebot_plugin_render.render import render_template
from nonebot_plugin_render.cache import creator

from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot.exception import FinishedException

sudoku = on_alconna(
    Alconna("sudoku", 
        Subcommand("new",Args["difficult_level",Literal["easy","medium","hard"],"easy"]),
        Subcommand("fill", Args["x",int], Args["y",int]),
        Subcommand("clear", Args["x",int], Args["y",int]),
        Subcommand("answer"),
        Subcommand("undo"),
        Subcommand("redo"),
    )
)
lang=LangHelper()
patch_matcher(sudoku)