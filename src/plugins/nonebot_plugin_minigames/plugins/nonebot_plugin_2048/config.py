from pydantic import BaseModel
from typing_extensions import TypedDict
from nonebot import get_plugin_config

COLOR = tuple[int, int, int]


class Colors(TypedDict):
    wall: COLOR
    null: COLOR
    word: COLOR
    block_2: COLOR
    block_4: COLOR
    block_8: COLOR
    block_16: COLOR
    block_32: COLOR
    block_64: COLOR
    block_128: COLOR
    block_256: COLOR
    block_512: COLOR
    block_1024: COLOR
    block_2048: COLOR


class Config(BaseModel):
    """Plugin Config Here"""

    mg2048_colors: Colors = {
        "wall": (184, 175, 158),
        "null": (204, 192, 178),
        "word": (255, 247, 235),
        "block_2": (238, 228, 218),
        "block_4": (236, 224, 200),
        "block_8": (242, 177, 121),
        "block_16": (245, 199, 49),
        "block_32": (245, 124, 95),
        "block_64": (246, 93, 59),
        "block_128": (237, 106, 113),
        "block_256": (237, 204, 97),
        "block_512": (236, 200, 80),
        "block_1024": (237, 197, 63),
        "block_2048": (255, 0, 0),
    }
    mg2048_font_size: int = 72


config = get_plugin_config(Config)
