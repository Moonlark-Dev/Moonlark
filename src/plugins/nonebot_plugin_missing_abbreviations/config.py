from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """“缩略” 的玩法参数。"""

    # 一次让模型生成多少道题（以 5 题为梯度单元）
    missing_abbreviations_generate_count: int = 20
    # 单次生成请求的超时（秒），避免模型挂住整局游戏
    missing_abbreviations_generate_timeout: int = 600
    # 缓存中的题目少于该值时后台预生成一批
    missing_abbreviations_cache_low_water: int = 5
    # 每局最多作答次数（猜错扣减，免费提示与误填原词全称不扣减）
    missing_abbreviations_max_attempts: int = 10
    # 三分钟没有任何消息时放弃并公布答案
    missing_abbreviations_idle_timeout: int = 180
    # 猜中奖励的 VimCoin（免费使用提示不扣减奖励）
    missing_abbreviations_reward: float = 3.0
    # 本地保留多少条近期原词 / 答案 / 题面记录用于去重
    missing_abbreviations_history_size: int = 80


config = get_plugin_config(Config)
