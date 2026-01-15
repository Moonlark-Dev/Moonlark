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
from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import Sticker
from .sticker_similarity import calculate_perceptual_hash


async def _check_and_update_sticker_hashes() -> None:
    """
    检查所有表情包是否都保存了感知哈希，如果没有则计算并保存
    """
    async with get_session() as session:
        # 查询所有没有感知哈希的表情包
        stickers_without_hash = (
            await session.scalars(
                select(Sticker).where((Sticker.p_hash == None) | (Sticker.p_hash == ""))
            )
        ).all()

        if not stickers_without_hash:
            logger.info("[Chat] 所有表情包都已有 pHash")
            return

        logger.info(f"[Chat] 发现 {len(stickers_without_hash)} 个表情包缺少 pHash，开始计算...")

        success_count = 0
        fail_count = 0

        for sticker in stickers_without_hash:
            try:
                # 计算感知哈希
                p_hash = await asyncio.get_running_loop().run_in_executor(
                    None, calculate_perceptual_hash, sticker.raw
                )

                if p_hash:
                    # 更新数据库
                    sticker.p_hash = p_hash
                    success_count += 1
                    logger.debug(f"[Chat] 已计算表情包 {sticker.id} 的 pHash: {p_hash}")
                else:
                    logger.warning(f"[Chat] 无法计算表情包 {sticker.id} 的 pHash")
                    fail_count += 1

            except Exception as e:
                logger.error(f"[Chat] 处理表情包 {sticker.id} 时出错: {e}")
                fail_count += 1

        # 提交所有更改
        await session.commit()
        logger.success(f"[Chat] pHash 初始化完成: 成功 {success_count} 个，失败 {fail_count} 个")


def check_and_update_sticker_hashes() -> None:
    """
    同步接口：检查并更新表情包哈希
    用于在启动时或迁移时调用
    """
    asyncio.run(_check_and_update_sticker_hashes())


async def initialize_sticker_hashes() -> None:
    """
    异步接口：检查并更新表情包哈希
    用于在运行时调用
    """
    await _check_and_update_sticker_hashes()