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

from PIL import Image
from ..enums import Blocks
from ...config import config
from nonebot_plugin_localstore import get_config_dir
from nonebot.log import logger
import traceback

# 加载默认资源
base_path = config.ftt_assets_path or get_config_dir("nonebot-plugin-finding-the-trail")
try:
    BLOCKS = {
        Blocks.NULL: Image.open(base_path.joinpath("stone_bricks.png")),
        Blocks.WALL: Image.open(base_path.joinpath("bricks.png")),
        Blocks.START: Image.open(base_path.joinpath("iron_block.png")),
        Blocks.END: Image.open(base_path.joinpath("diamond_block.png")),
        Blocks.PISTON: Image.open(base_path.joinpath("piston_top.png")),
        Blocks.SAND: Image.open(base_path.joinpath("sand.png")),
        Blocks.COBWEB: Image.open(base_path.joinpath("cobweb.png")),
        Blocks.PORTAL: Image.open(base_path.joinpath("portal.png")),
        Blocks.GOLD_PISTON: Image.open(base_path.joinpath("gold_piston_top.png")),
    }
except FileNotFoundError:
    logger.error(f"加载贴图失败（文件缺失）: {traceback.format_exc()}")


def generate_map_image(game_map: list[list[Blocks]]) -> Image.Image:
    """
    生成地图图片
    :param game_map: 游戏地图
    """
    image = Image.new("RGB", (len(game_map[0]) * 16, len(game_map) * 16), (51, 255, 255))
    for row in range(len(game_map)):
        for column in range(len(game_map[row])):
            item = game_map[row][column]
            x0 = column * 16
            y0 = row * 16
            image.paste(BLOCKS[item], (x0, y0))
    return image
