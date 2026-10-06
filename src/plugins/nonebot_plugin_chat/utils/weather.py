"""和风天气客户端与日期辅助

- 每日天气：用于会话信息、博客、日记、计划生成的"当天天气"
- 实时天气：get_weather 工具
- 未配置 QWEATHER_API_KEY / 经纬度时，所有功能自动禁用（fallback 到旧行为）

每日天气会缓存在 LocalStore 里（按日期），会话元数据（meta 消息）直接读缓存，
跨天后的第一次获取会重新请求并刷新缓存。
"""

import json
from datetime import datetime
from typing import Optional

import aiofiles
import httpx
import nonebot_plugin_localstore as store
from nonebot.log import logger

from ..config import config

# API Host：标准订阅为账号专属域名；未配置时回退到公共地址（公共地址自 2026 年起逐步停用）
DEV_API_BASE = (config.qweather_api_host or "https://devapi.qweather.com").rstrip("/")
GEO_API_BASE = (config.qweather_geo_api_host or "https://geoapi.qweather.com").rstrip("/")

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def is_weather_configured() -> bool:
    return bool(config.qweather_api_key)


def is_moonlark_location_configured() -> bool:
    return config.moonlark_latitude is not None and config.moonlark_longitude is not None


def get_weekday_text(dt: Optional[datetime] = None) -> str:
    """获取中文星期，如"星期六" """
    return WEEKDAYS[(dt or datetime.now()).weekday()]


async def _qweather_request(base_url: str, path: str, params: dict[str, str]) -> Optional[dict]:
    """请求和风天气 API，成功（code=200）时返回 JSON，否则返回 None"""
    request_params = {"key": config.qweather_api_key, "lang": "zh", **params}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{base_url}/{path}", params=request_params)
            if response.status_code != 200:
                return None
            data = response.json()
            if data.get("code") != "200":
                return None
            return data
    except Exception:
        return None


async def get_daily_weather_text() -> Optional[str]:
    """获取 Moonlark 所在地今天的天气文本，如"多云，22℃~31℃"。

    未配置经纬度或 API Key 时返回 None（不启用该功能）。
    """
    if not is_weather_configured() or not is_moonlark_location_configured():
        return None

    location = f"{config.moonlark_longitude},{config.moonlark_latitude}"
    data = await _qweather_request(DEV_API_BASE, "v7/weather/3d", {"location": location})
    if data is None or not data.get("daily"):
        return None

    today = data["daily"][0]
    return f"{today.get('textDay', '未知')}，{today.get('tempMin', '?')}℃~{today.get('tempMax', '?')}℃"


def _daily_weather_cache_file():
    directory = store.get_cache_dir("nonebot_plugin_chat")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "daily_weather.json"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


async def read_daily_weather_cache() -> Optional[str]:
    """读取当天的天气缓存，缓存不存在或已跨天时返回 None"""
    path = _daily_weather_cache_file()
    if not path.exists():
        return None
    try:
        async with aiofiles.open(path, encoding="utf-8") as file:
            cached = json.loads(await file.read())
    except Exception as e:
        logger.debug(f"读取天气缓存失败: {e}")
        return None
    if not isinstance(cached, dict) or cached.get("date") != _today():
        return None
    text = cached.get("text")
    return text if isinstance(text, str) and text else None


async def write_daily_weather_cache(text: str) -> None:
    path = _daily_weather_cache_file()
    payload = {"date": _today(), "text": text, "updated_at": datetime.now().isoformat()}
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.debug(f"写入天气缓存失败: {e}")


async def get_cached_daily_weather_text() -> Optional[str]:
    """获取当天的天气文本：优先读 LocalStore 缓存，跨天后重新获取并刷新缓存"""
    cached = await read_daily_weather_cache()
    if cached is not None:
        return cached
    text = await get_daily_weather_text()
    if text:
        await write_daily_weather_cache(text)
    return text


async def refresh_daily_weather_cache() -> Optional[str]:
    """强制刷新当天天气缓存（每日定时任务调用）"""
    text = await get_daily_weather_text()
    if text:
        await write_daily_weather_cache(text)
    return text
