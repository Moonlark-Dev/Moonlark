#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################
from PIL.ImageDraw import ImageDraw

from .config import config
from PIL.Image import Image as ImageType
from PIL import Image
from PIL.ImageFont import load_default


def draw_number_block(number: int) -> ImageType:
    img = Image.new("RGB", (105, 105), config.mg2048_colors[f"block_{number}"])
    font = load_default(config.mg2048_font_size)
    length = font.getlength(str(number))
    pos = (105 - config.mg2048_font_size) / 2, (105 - length) / 2
    draw = ImageDraw(img)
    draw.text(pos, str(number), config.mg2048_colors["word"], font)
    return img


def get_null_block() -> ImageType:
    return Image.new("RGB", (105, 105), config.mg2048_colors["null"])


def draw_map(game_map: list[list[int]]) -> Image:
    image = Image.new("RGB", (500, 500), config.mg2048_colors["wall"])
    x = 16
    y = 16
    for row in game_map:
        for block in row:
            if block == 0:
                image.paste(get_null_block(), (x, y))
            else:
                image.paste(draw_number_block(block), (x, y))
            x += 121
        y += 121
        x = 0
    return image
