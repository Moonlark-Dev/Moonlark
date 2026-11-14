"""模型配置管理模块

与 ``nonebot_plugin_openai.utils.model_config`` 行为一致：使用数据库存储默认模型
与应用特定模型，未配置时回落到插件配置里的默认模型。
"""

from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select

from ..config import config

# 特殊键名用于存储默认模型
DEFAULT_MODEL_KEY = "__default__"


async def get_default_model() -> str:
    """获取默认模型"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        result = await session.scalar(
            select(GeminiModelConfig.model_name).where(GeminiModelConfig.config_key == DEFAULT_MODEL_KEY)
        )
        return result if result else config.gemini_default_model


async def set_default_model(model: str) -> None:
    """设置默认模型"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        existing = await session.scalar(
            select(GeminiModelConfig).where(GeminiModelConfig.config_key == DEFAULT_MODEL_KEY)
        )
        if existing:
            existing.model_name = model
        else:
            session.add(
                GeminiModelConfig(
                    config_key=DEFAULT_MODEL_KEY,
                    model_name=model,
                    config_type="default",
                )
            )
        await session.commit()


async def get_model_for_identify(identify: str) -> str:
    """获取指定应用的模型，如果没有特定配置则返回默认模型"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        result = await session.scalar(
            select(GeminiModelConfig.model_name).where(GeminiModelConfig.config_key == identify)
        )
        if result:
            return result
        return await get_default_model()


async def is_default_model_for_identify(identify: str) -> bool:
    """判断指定应用是否使用默认模型"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        result = await session.scalar(select(GeminiModelConfig).where(GeminiModelConfig.config_key == identify))
        return result is None


async def set_model_for_identify(identify: str, model: str) -> None:
    """设置指定应用的模型"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        existing = await session.scalar(select(GeminiModelConfig).where(GeminiModelConfig.config_key == identify))
        if existing:
            existing.model_name = model
        else:
            session.add(
                GeminiModelConfig(
                    config_key=identify,
                    model_name=model,
                    config_type="override",
                )
            )
        await session.commit()


async def remove_model_for_identify(identify: str) -> bool:
    """删除指定应用的模型配置，使其使用默认模型"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        existing = await session.scalar(select(GeminiModelConfig).where(GeminiModelConfig.config_key == identify))
        if existing:
            await session.delete(existing)
            await session.commit()
            return True
        return False


async def get_model_override() -> dict[str, str]:
    """获取所有应用特定的模型配置"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        results = await session.execute(
            select(GeminiModelConfig.config_key, GeminiModelConfig.model_name).where(
                GeminiModelConfig.config_type == "override"
            )
        )
        return {key: model for key, model in results.all()}


async def clear_identify_models() -> None:
    """删除所有应用特定的模型配置（仅用于测试与维护）"""
    async with get_session() as session:
        from ..models import GeminiModelConfig

        await session.execute(delete(GeminiModelConfig).where(GeminiModelConfig.config_type == "override"))
        await session.commit()
