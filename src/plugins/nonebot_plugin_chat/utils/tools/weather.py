"""get_weather 工具：从和风天气获取某个城市的实时天气"""

from nonebot_plugin_chat.types import GetTextFunc

from ...config import config
from ..weather import DEV_API_BASE, GEO_API_BASE, _qweather_request


async def get_weather(city: str, get_text: GetTextFunc) -> str:
    """获取指定城市的实时天气（和风天气）"""
    if not config.qweather_api_key:
        return await get_text("weather.unavailable")

    geo_data = await _qweather_request(GEO_API_BASE, "v2/city/lookup", {"location": city})
    if geo_data is None or not geo_data.get("location"):
        return await get_text("weather.location_not_found", city)
    location = geo_data["location"][0]

    now_data = await _qweather_request(DEV_API_BASE, "v7/weather/now", {"location": location["id"]})
    if now_data is None or not now_data.get("now"):
        return await get_text("weather.failed", city)
    now = now_data["now"]

    return await get_text(
        "weather.now",
        location.get("name", city),
        now.get("text", "未知"),
        now.get("temp", "?"),
        now.get("feelsLike", "?"),
        now.get("windDir", "未知"),
        now.get("windScale", "?"),
        now.get("humidity", "?"),
        now.get("obsTime", ""),
    )
