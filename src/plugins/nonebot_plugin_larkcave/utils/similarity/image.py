import asyncio
import io
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from ...types import CheckPassedResult, CheckFailedResult, CheckResult
from ..encoder import calculate_perceptual_hash
import imagehash

from nonebot_plugin_larkcave.models import CaveData, ImageData


def compare_hash(hash1: str, hash2: str) -> float:
    """
    比较两个感知哈希的相似度
    :param hash1: 第一个哈希值
    :param hash2: 第二个哈希值
    :return: 相似度分数 (0-1)，1 表示完全相同
    """
    if not hash1 or not hash2:
        return 0.0
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        # 计算汉明距离，转换为相似度分数
        # hash_size=16 时，最大距离为 256 (16*16)
        max_distance = len(hash1) * 4  # 每个十六进制字符代表4位
        distance = h1 - h2
        similarity = 1 - (distance / max_distance)
        return max(0.0, similarity)
    except Exception:
        return 0.0


async def check_image(posting: bytes, session: async_scoped_session, name: str) -> CheckResult:
    """
    投稿图片相似度检查（使用感知哈希）
    :param posting: 正在投稿的图片
    :param session: 数据库会话
    :param name: 图片文件名
    :return: 检查结果
    """
    # 计算待投稿图片的感知哈希
    posting_hash = await asyncio.get_running_loop().run_in_executor(
        None, calculate_perceptual_hash, posting
    )
    
    if not posting_hash:
        # 无法计算哈希，直接通过
        return CheckPassedResult(passed=True)
    
    # 获取所有已存储图片的哈希值
    image_data_list = (await session.scalars(select(ImageData))).all()
    
    # 比较哈希值
    for image_data in image_data_list:
        if not image_data.p_hash:
            continue
        
        similarity = compare_hash(posting_hash, image_data.p_hash)
        
        # 相似度阈值设为 0.9
        if similarity >= 0.9:
            cave = await session.get_one(CaveData, {"id": image_data.belong})
            return CheckFailedResult(
                passed=False, similar_cave=cave, similarity=similarity
            )
    
    return CheckPassedResult(passed=True)
