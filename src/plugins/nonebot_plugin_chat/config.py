from nonebot import get_plugin_config
from pydantic import BaseModel


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


config = get_plugin_config(Config)
