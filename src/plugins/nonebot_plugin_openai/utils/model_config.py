"""
模型配置管理模块
使用 localstore 存储模型配置，支持默认模型和应用特定模型
"""

import json
from typing import TypedDict, Optional

import aiofiles
from nonebot_plugin_localstore import get_data_file

from ..config import config


class ModelConfigData(TypedDict):
    default_model: str
    model_override: dict[str, str]


# 获取配置文件路径
config_file = get_data_file("nonebot_plugin_openai", "model_config.json")


async def load_config() -> ModelConfigData:
    """加载模型配置，如果不存在则从 .env 创建"""
    if config_file.exists():
        async with aiofiles.open(config_file, encoding="utf-8") as f:
            return ModelConfigData(**json.loads(await f.read()))
    # 从 .env 配置创建初始配置
    data = ModelConfigData(
        default_model=config.openai_default_model,
        model_override=dict(config.model_override),
    )
    await save_config(data)
    return data


async def save_config(data: ModelConfigData) -> None:
    """保存模型配置"""
    async with aiofiles.open(config_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, indent=4, ensure_ascii=False))


async def get_default_model() -> str:
    """获取默认模型"""
    data = await load_config()
    return data["default_model"]


async def set_default_model(model: str) -> None:
    """设置默认模型"""
    data = await load_config()
    data["default_model"] = model
    await save_config(data)


async def get_model_for_identify(identify: str) -> str:
    """获取指定应用的模型，如果没有特定配置则返回默认模型"""
    data = await load_config()
    return data["model_override"].get(identify, data["default_model"])


async def set_model_for_identify(identify: str, model: str) -> None:
    """设置指定应用的模型"""
    data = await load_config()
    data["model_override"][identify] = model
    await save_config(data)


async def remove_model_for_identify(identify: str) -> bool:
    """删除指定应用的模型配置，使其使用默认模型

    返回 True 表示成功删除，False 表示该应用没有特定配置
    """
    data = await load_config()
    if identify in data["model_override"]:
        del data["model_override"][identify]
        await save_config(data)
        return True
    return False


async def get_model_override() -> dict[str, str]:
    """获取所有应用特定的模型配置"""
    data = await load_config()
    return data["model_override"]
