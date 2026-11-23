from typing import Literal

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """模拟股票市场配置"""

    # 每笔交易的手续费率
    trade_fee_rate: float = 0.01
    # 初始价格（VimCoin/股）
    trade_initial_price: float = 10.0
    # 总股本
    trade_total_shares: int = 100000
    # 每人每天买入/卖出各自的限额
    trade_daily_limit: int = 1000
    # 单笔买卖冲击上限
    trade_max_impact: float = 0.01
    # K 线图固定展示的蜡烛数量（含前一交易日，不足时向前滚动补齐）
    trade_chart_candles: int = 120
    # 日 K 线历史固定展示的交易日数量（不足时所有蜡烛挤在右侧）
    trade_history_candles: int = 60
    # 收益排行榜展示的上榜人数
    trade_rank_size: int = 10
    # CandleBridge 波动强度预设（low / medium / high）
    trade_intensity: Literal["low", "medium", "high"] = "medium"
    # CandleBridge 细步分辨率（1 或 5 秒）
    trade_fine_seconds: Literal[1, 5] = 5
    # CandleBridge 基础每分钟波动率（百分比）
    trade_base_volatility: float = 0.09
    # CandleBridge Student-t 自由度（3..30）
    trade_df: int = 6
    # CandleBridge EWMA 波动率聚类衰减系数（0 <= decay < 1）
    trade_decay: float = 0.9
    # CandleBridge 对数正态波动冲击强度（0..2）
    trade_shock: float = 0.38
    # CandleBridge 每分钟跳跃概率（百分比，0.02 表示 0.02%/分）
    trade_jump_probability: float = 0.02
    # CandleBridge 跳跃幅度下限/上限（百分比）
    trade_jump_minimum: float = 0.4
    trade_jump_maximum: float = 1.8
    # CandleBridge 三态机制波动率倍率（静默 / 高波动 / 趋势）
    trade_low_multiplier: float = 0.5
    trade_high_multiplier: float = 2.1
    trade_trend_multiplier: float = 1.05
    # CandleBridge 单态持续时长范围（分钟）
    trade_state_minimum: float = 30.0
    trade_state_maximum: float = 360.0
    # CandleBridge 趋势态每分钟漂移强度（百分比）
    trade_trend_strength: float = 0.0075
    # 08:00 隔夜跳空基准等效演进时长（分钟），0 表示不跳空
    trade_open_gap_minutes: int = 30
    # 每天开盘时是否围绕基准配置随机抽取当日 CandleBridge 参数与跳空时长（增加行情多样性）
    trade_randomize_daily_model: bool = True


config = get_plugin_config(Config)
