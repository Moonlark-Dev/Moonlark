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
    # K 线图固定展示的蜡烛数量（含前一交易日，不足时向前滚动补齐）
    trade_chart_candles: int = 120
    # 隔夜跳空幅度上限（相对前一交易日收盘价；实际幅度至少 0.5%）
    trade_gap_sigma: float = 0.03
    # 布朗桥插值幅度（相对单次 tick 的 trade_sigma），用于生成影线
    trade_bridge_vol: float = 0.5


config = get_plugin_config(Config)
