"""和风天气客户端与日期辅助

- 每日天气：用于会话信息、博客、日记、计划生成的"当天天气"
- 实时天气：get_weather 工具
- 未配置 QWEATHER_API_KEY / 经纬度时，所有功能自动禁用（fallback 到旧行为）
"""

from datetime import datetime
from typing import Any, Optional

import httpx

from ..config import config

# API Host：标准订阅为账号专属域名；未配置时回退到公共地址（公共地址自 2026 年起逐步停用）
DEV_API_BASE = (config.qweather_api_host or "https://devapi.qweather.com").rstrip("/")
GEO_API_BASE = (config.qweather_geo_api_host or "https://geoapi.qweather.com").rstrip("/")

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# 每日天气缓存：成功 30 分钟、失败 5 分钟，避免频繁请求
_daily_cache: dict[str, Any] = {"time": None, "text": None, "success": False}


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

    now = datetime.now()
    cached = _daily_cache.get("time")
    if cached is not None:
        ttl = 1800 if _daily_cache.get("success") else 300
        if (now - cached).total_seconds() < ttl:
            return _daily_cache.get("text")

    location = f"{config.moonlark_longitude},{config.moonlark_latitude}"
    data = await _qweather_request(DEV_API_BASE, "v7/weather/3d", {"location": location})
    if data is None or not data.get("daily"):
        _daily_cache.update(time=now, text=None, success=False)
        return None

    today = data["daily"][0]
    text = f"{today.get('textDay', '未知')}，{today.get('tempMin', '?')}℃~{today.get('tempMax', '?')}℃"
    _daily_cache.update(time=now, text=text, success=True)
    return text
