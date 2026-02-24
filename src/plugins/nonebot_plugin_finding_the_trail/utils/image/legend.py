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

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from ..enums import Blocks
from .generator import BLOCKS


def generate_legend_image(block_names: dict[Blocks, str], block_descs: dict[Blocks, str], title: str) -> bytes:
    """
    生成图例图片
    :param block_names: 方块名称字典
    :param block_descs: 方块描述字典
    :param title: 图例标题
    :return: PNG 图片字节数据
    """
    # 定义方块顺序
    block_order = [
        Blocks.NULL,
        Blocks.WALL,
        Blocks.START,
        Blocks.END,
        Blocks.PISTON,
        Blocks.SAND,
        Blocks.PORTAL,
        Blocks.COBWEB,
        Blocks.GOLD_PISTON,
    ]

    # 图片尺寸设置
    block_size = 32  # 方块显示大小
    padding = 20  # 边距
    row_height = 50  # 每行高度
    title_height = 50  # 标题高度

    # 计算图片尺寸
    width = 600
    height = title_height + len(block_order) * row_height + padding * 2

    # 创建图片
    image = Image.new("RGB", (width, height), (40, 44, 52))  # 深色背景
    draw = ImageDraw.Draw(image)

    # 尝试加载字体
    try:
        title_font = ImageFont.truetype("simhei.ttf", 28)
        name_font = ImageFont.truetype("simhei.ttf", 20)
        desc_font = ImageFont.truetype("simhei.ttf", 14)
    except:
        title_font = ImageFont.load_default()
        name_font = ImageFont.load_default()
        desc_font = ImageFont.load_default()

    # 绘制标题
    draw.text((padding, padding), title, (255, 255, 255), font=title_font)

    # 绘制每个方块
    y_offset = title_height + padding
    for block in block_order:
        # 绘制方块图片
        if block in BLOCKS:
            block_img = BLOCKS[block].resize((block_size, block_size), Image.LANCZOS)
            image.paste(block_img, (padding, y_offset + (row_height - block_size) // 2))

        # 绘制方块名称
        name_x = padding + block_size + 15
        draw.text((name_x, y_offset + 5), block_names.get(block, "Unknown"), (255, 255, 255), font=name_font)

        # 绘制方块描述
        draw.text((name_x, y_offset + 28), block_descs.get(block, ""), (180, 180, 180), font=desc_font)

        y_offset += row_height

    # 保存为字节
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
