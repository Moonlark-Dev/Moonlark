from typing import Any, Optional

from nonebot import get_plugin_config
from pydantic import BaseModel, field_validator


class RuaReactionConfig(BaseModel):
    enjoy: str = "66"
    dodge: str = "10"
    bite: str = "128074"
    pending: str = "181"


class JudgeReactionConfig(BaseModel):
    add: str = "66"
    sub: str = "106"


class Config(BaseModel):
    """Plugin Config Here"""

    command_start: list[str] = ["/"]
    metaso_api_key: str = ""
    napcat_bot_ids: list[str] = []
    # VM 远程执行服务配置
    vm_api_url: str = ""  # VM 服务地址，如 http://localhost:8000
    vm_api_token: str = ""  # VM API 鉴权 Token
    moonlark_api_base: str = "http://localhost:8080"  # Moonlark API 基础地址
    rua_reaction_config: RuaReactionConfig = RuaReactionConfig()
    judge_reaction_config: JudgeReactionConfig = JudgeReactionConfig()
    # 合并转发消息自动总结阈值（字符数），超过此长度的转发消息将调用 AI 生成摘要
    forward_summary_threshold: int = 2000
    # Meme-Search 外部梗图源配置
    meme_search_base_url: str = "https://meme-search.xxtg666.top"
    # 和风天气 API Key（https://dev.qweather.com），不填写则天气相关功能不启用
    qweather_api_key: str = ""
    # 和风天气 API Host：标准订阅为账号专属域名（如 https://xxxx.re.qweatherapi.com），
    # 不填写则使用公共地址 devapi.qweather.com（公共地址自 2026 年起逐步停用）
    qweather_api_host: Optional[str] = None
    # 和风天气 GeoAPI Host（城市搜索）：专属 Host 通常不提供城市搜索接口，
    # 需要时可单独指定；不填写则使用公共地址 geoapi.qweather.com
    qweather_geo_api_host: Optional[str] = None
    # Moonlark 所在地区的经纬度，不填写则不启用所在地每日天气
    moonlark_latitude: Optional[float] = None
    moonlark_longitude: Optional[float] = None

    @field_validator(
        "qweather_api_host",
        "qweather_geo_api_host",
        "moonlark_latitude",
        "moonlark_longitude",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value


config = get_plugin_config(Config)
