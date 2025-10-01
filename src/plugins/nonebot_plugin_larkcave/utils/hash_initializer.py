#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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

import asyncio
import zlib
import aiofiles
from nonebot import logger
from nonebot_plugin_orm import async_scoped_session, get_session
from sqlalchemy import select

from ..models import ImageData
from .decoder import data_dir
from .encoder import calculate_perceptual_hash


async def _check_and_update_hashes() -> None:
    """
    检查所有图片是否都保存了感知哈希，如果没有则计算并保存
    """
    async with get_session() as session:
        # 查询所有没有感知哈希的图片
        images_without_hash = (
            await session.scalars(select(ImageData).where((ImageData.p_hash == None) | (ImageData.p_hash == "")))
        ).all()

        if not images_without_hash:
            logger.info("所有图片都已有 pHash")
            return

        logger.info(f"发现 {len(images_without_hash)} 张图片缺少 pHash，开始计算...")

        success_count = 0
        fail_count = 0

        for image_data in images_without_hash:
            try:
                # 读取图片文件
                file_path = data_dir.joinpath(image_data.file_id)
                if not file_path.exists():
                    logger.warning(f"图片文件不存在: {image_data.file_id} (ID: {image_data.id})")
                    fail_count += 1
                    continue

                async with aiofiles.open(file_path, "rb") as f:
                    compressed_data = await f.read()
                    image_bytes = zlib.decompress(compressed_data)

                # 计算感知哈希
                p_hash = calculate_perceptual_hash(image_bytes)

                if p_hash:
                    # 更新数据库
                    image_data.p_hash = p_hash
                    success_count += 1
                    logger.debug(f"已计算图片 {image_data.id} 的 pHash: {p_hash}")
                else:
                    logger.warning(f"无法计算图片 {image_data.id} 的 pHash")
                    fail_count += 1

            except Exception as e:
                logger.error(f"处理图片 {image_data.id} 时出错: {e}")
                fail_count += 1

        # 提交所有更改
        await session.commit()
        logger.success(f"pHash 初始化完成: 成功 {success_count} 张，失败 {fail_count} 张")


def check_and_update_hashes() -> None:
    asyncio.run(_check_and_update_hashes())