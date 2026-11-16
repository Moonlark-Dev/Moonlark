from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """“有无有无” 的玩法参数。"""

    # 一次让模型生成多少道题（题目提示词要求一次生成 20 个）
    has_or_not_generate_count: int = 20
    # 单次生成请求的超时（秒），避免模型挂住整局游戏
    has_or_not_generate_timeout: int = 180
    # 缓存中的题目少于该值时后台预生成一批
    has_or_not_cache_low_water: int = 5
    # 每局最多作答次数（含猜错；猜中立即结束）
    has_or_not_max_attempts: int = 10
    # 三分钟没有任何消息时放弃并公布答案
    has_or_not_idle_timeout: int = 180
    # 猜中奖励的 VimCoin
    has_or_not_reward: float = 3.0
    # 本地保留多少个近期答案 / 六个词语组合用于去重
    has_or_not_history_size: int = 60
    # Decisions API 判定作答正确的 Noul 概率阈值
    has_or_not_judge_threshold: float = 0.5


config = get_plugin_config(Config)
