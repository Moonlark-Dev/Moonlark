"""
模型配置管理模块
使用 localstore 存储模型配置，支持默认模型和应用特定模型
"""

import json
from datetime import datetime, timedelta
from typing import TypedDict, Optional

import aiofiles
from nonebot_plugin_localstore import get_data_file
from nonebot import logger

from ..config import config


class ModelConfigData(TypedDict):
    default_model: str
    model_override: dict[str, str]


class TimeoutStateData(TypedDict):
    timeout_records: list[str]  # ISO 格式的时间戳列表
    backup_mode_until: Optional[str]  # 备用模式结束时间，ISO 格式


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
    """获取指定应用的模型，如果没有特定配置则返回默认模型
    
    注意：如果处于备用模式且该应用使用默认模型，则返回备用模型
    """
    data = await load_config()
    
    # 如果该 identify 有特定配置，直接返回
    if identify in data["model_override"]:
        return data["model_override"][identify]
    
    # 否则返回有效的默认模型（可能是备用模型）
    return await get_effective_default_model()

async def is_default_model_for_identify(identify: str) -> bool:
    """判断指定应用的模型是否为默认模型"""
    data = await load_config()
    return data["model_override"].get(identify) is None

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


# ===== 超时状态管理 =====

# 超时状态文件路径
timeout_state_file = get_data_file("nonebot_plugin_openai", "timeout_state.json")


async def load_timeout_state() -> TimeoutStateData:
    """加载超时状态"""
    if timeout_state_file.exists():
        async with aiofiles.open(timeout_state_file, encoding="utf-8") as f:
            return TimeoutStateData(**json.loads(await f.read()))
    # 创建初始状态
    data = TimeoutStateData(
        timeout_records=[],
        backup_mode_until=None,
    )
    await save_timeout_state(data)
    return data


async def save_timeout_state(data: TimeoutStateData) -> None:
    """保存超时状态"""
    async with aiofiles.open(timeout_state_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, indent=4, ensure_ascii=False))


async def is_backup_mode_active() -> bool:
    """检查是否处于备用模型模式"""
    state = await load_timeout_state()
    if state["backup_mode_until"] is None:
        return False
    backup_until = datetime.fromisoformat(state["backup_mode_until"])
    if datetime.now() >= backup_until:
        # 备用模式已过期，清理状态
        state["backup_mode_until"] = None
        await save_timeout_state(state)
        return False
    return True


async def get_backup_model() -> Optional[str]:
    """获取备用模型，如果未配置则返回 None"""
    data = await load_config()
    return data["model_override"].get(config.backup_model_identify)


async def record_timeout_and_check_backup() -> bool:
    """
    记录一次超时事件，并检查是否需要切换到备用模型
    
    返回 True 表示已切换到备用模型，False 表示未切换
    """
    now = datetime.now()
    state = await load_timeout_state()
    
    # 如果已经在备用模式，不需要再次处理
    if state["backup_mode_until"] is not None:
        backup_until = datetime.fromisoformat(state["backup_mode_until"])
        if now < backup_until:
            logger.debug("Already in backup mode, skipping timeout record")
            return False
    
    # 清理过期的超时记录（只保留窗口时间内的）
    window_start = now - timedelta(hours=config.timeout_window_hours)
    valid_records = [
        ts for ts in state["timeout_records"]
        if datetime.fromisoformat(ts) > window_start
    ]
    
    # 添加新的超时记录
    valid_records.append(now.isoformat())
    state["timeout_records"] = valid_records
    
    logger.info(f"Recorded timeout event, total timeouts in window: {len(valid_records)}")
    
    # 检查是否超过阈值
    if len(valid_records) > config.timeout_threshold:
        # 检查是否配置了备用模型
        backup_model = await get_backup_model()
        if backup_model is None:
            logger.warning("Timeout threshold exceeded but no backup model configured")
            await save_timeout_state(state)
            return False
        
        # 切换到备用模型模式
        backup_until = now + timedelta(hours=config.backup_model_duration_hours)
        state["backup_mode_until"] = backup_until.isoformat()
        state["timeout_records"] = []  # 清空记录
        await save_timeout_state(state)
        
        logger.warning(
            f"Timeout threshold exceeded ({len(valid_records)} > {config.timeout_threshold}), "
            f"switching to backup model until {backup_until.isoformat()}"
        )
        return True
    
    await save_timeout_state(state)
    return False


async def get_effective_default_model() -> str:
    """
    获取有效的默认模型
    如果处于备用模式且配置了备用模型，返回备用模型
    否则返回正常的默认模型
    """
    if await is_backup_mode_active():
        backup_model = await get_backup_model()
        if backup_model is not None:
            logger.debug(f"Using backup model: {backup_model}")
            return backup_model
    return await get_default_model()
