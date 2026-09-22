"""
模型配置管理模块
使用数据库存储模型配置，支持默认模型和应用特定模型
"""

from typing import TYPE_CHECKING

from nonebot_plugin_orm import get_session
from sqlalchemy import select, delete

from ..config import config

if TYPE_CHECKING:
    from ..models import OpenAIModelConfig


# 特殊键名用于存储默认模型
DEFAULT_MODEL_KEY = "__default__"


async def get_default_model() -> str:
    """获取默认模型"""
    async with get_session() as session:
        from ..models import OpenAIModelConfig

        result = await session.scalar(
            select(OpenAIModelConfig.model_name).where(OpenAIModelConfig.config_key == DEFAULT_MODEL_KEY)
        )
        return result if result else config.openai_default_model


async def set_default_model(model: str) -> None:
    """设置默认模型"""
    async with get_session() as session:
        from ..models import OpenAIModelConfig

        existing = await session.scalar(
            select(OpenAIModelConfig).where(OpenAIModelConfig.config_key == DEFAULT_MODEL_KEY)
        )
        if existing:
            existing.model_name = model
        else:
            session.add(
                OpenAIModelConfig(
                    config_key=DEFAULT_MODEL_KEY,
                    model_name=model,
                    config_type="default",
                )
            )
        await session.commit()


async def get_model_for_identify(identify: str) -> str:
    """获取指定应用的模型，如果没有特定配置则返回默认模型"""
    async with get_session() as session:
        from ..models import OpenAIModelConfig

        # 先查找特定应用的配置
        result = await session.scalar(
            select(OpenAIModelConfig.model_name).where(OpenAIModelConfig.config_key == identify)
        )
        if result:
            return result
        # 没有特定配置则返回默认模型
        return await get_default_model()


async def is_default_model_for_identify(identify: str) -> bool:
    """判断指定应用的模型是否为默认模型"""
    async with get_session() as session:
        from ..models import OpenAIModelConfig

        result = await session.scalar(select(OpenAIModelConfig).where(OpenAIModelConfig.config_key == identify))
        return result is None


async def set_model_for_identify(identify: str, model: str) -> None:
    """设置指定应用的模型"""
    async with get_session() as session:
        from ..models import OpenAIModelConfig

        existing = await session.scalar(select(OpenAIModelConfig).where(OpenAIModelConfig.config_key == identify))
        if existing:
            existing.model_name = model
        else:
            session.add(
                OpenAIModelConfig(
                    config_key=identify,
                    model_name=model,
                    config_type="override",
                )
            )
        await session.commit()


async def remove_model_for_identify(identify: str) -> bool:
    """删除指定应用的模型配置，使其使用默认模型

    返回 True 表示成功删除，False 表示该应用没有特定配置
    """
    async with get_session() as session:
        from ..models import OpenAIModelConfig

        existing = await session.scalar(select(OpenAIModelConfig).where(OpenAIModelConfig.config_key == identify))
        if existing:
            await session.delete(existing)
            await session.commit()
            return True
        return False


async def get_model_override() -> dict[str, str]:
    """获取所有应用特定的模型配置"""
    async with get_session() as session:
        from ..models import OpenAIModelConfig

        results = await session.execute(
            select(OpenAIModelConfig.config_key, OpenAIModelConfig.model_name).where(
                OpenAIModelConfig.config_type == "override"
            )
        )
        return {key: model for key, model in results.all()}


# 迁移相关函数
async def migrate_from_json(data: dict) -> None:
    """从旧的 JSON 格式迁移数据到数据库

    data 格式: {"default_model": str, "model_override": dict[str, str]}
    """
    # 迁移默认模型
    if "default_model" in data:
        await set_default_model(data["default_model"])

    # 迁移应用特定配置
    if "model_override" in data:
        for identify, model in data["model_override"].items():
            await set_model_for_identify(identify, model)
