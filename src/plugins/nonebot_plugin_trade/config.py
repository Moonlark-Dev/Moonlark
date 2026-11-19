from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """模拟股票市场配置"""

    # 每次 tick 的最大波动幅度（相对价格）
    trade_sigma: float = 0.01
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


config = get_plugin_config(Config)
