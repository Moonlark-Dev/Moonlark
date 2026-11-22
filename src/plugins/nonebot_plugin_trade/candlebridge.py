"""CandleBridge K 线合成算法（Python 移植版）。

移植自 https://github.com/slwyts/candlebridge （MIT License）。

核心随机过程在细粒度步长（1s 或 5s）上演进：
1. Mulberry32 确定性 32 位伪随机数流驱动 Box–Muller 标准正态采样；
2. 三态市场机制切换（静默 0.52 / 高波动 0.28 / 趋势 0.20），持续时间在
   ``[state_minimum, state_maximum]`` 分钟内随机抽取，趋势态带随机方向漂移；
3. 对数正态波动冲击与 EWMA 波动率聚类（``decay`` / ``shock``）；
4. 单位方差标准化 Student-t 肥尾扰动（``df > 2``）；
5. 稀疏随机跳跃冲击（``jump_probability`` / ``jump_minimum`` / ``jump_maximum``）；
6. 批量生成模式支持可选的对数收益桥终点锁定（``lock_target``）与价格边界拒绝采样；
   流式模式通过持久化 ``PathState`` 无缝按根推进，在无外力冲击时与批量自由路径一致。
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass, replace
from typing import Literal, Optional

Intensity = Literal["low", "medium", "high"]
FineResolutionSeconds = Literal[1, 5]
ExecutionPoint = tuple[int, float]
CandleBridgeErrorCode = Literal[
    "INVALID_PRICE_RANGE",
    "INVALID_INTERVAL",
    "INVALID_PARAMETERS",
    "PATH_TOO_LONG",
    "GENERATION_FAILED",
]

INTENSITY_SCALE: dict[Intensity, float] = {
    "low": 0.00055 / 0.0009,
    "medium": 1.0,
    "high": 0.0013 / 0.0009,
}

_UINT32_MASK = 0xFFFFFFFF
_UINT32_MAX = 4_294_967_295
_UINT32_MOD = 4_294_967_296.0
_MAX_SAFE_TIMESTAMP_MS = 8_640_000_000_000_000
_MAX_LOG_RETURN = 50.0


class CandleBridgeError(Exception):
    """CandleBridge 参数校验或路径采样失败时抛出的结构化异常。"""

    def __init__(self, code: CandleBridgeErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelParameters:
    """CandleBridge 随机路径生成器的统计模型参数（与上游 DEFAULT_MODEL 保持一致）。"""

    seed: int = 20261007
    fine_seconds: FineResolutionSeconds = 5
    df: int = 6
    decay: float = 0.9
    base_volatility: float = 0.09
    jump_probability: float = 0.02
    jump_minimum: float = 0.4
    jump_maximum: float = 1.8
    shock: float = 0.38
    low_multiplier: float = 0.5
    high_multiplier: float = 2.1
    trend_multiplier: float = 1.05
    state_minimum: float = 30.0
    state_maximum: float = 360.0
    trend_strength: float = 0.0075
    intensity: Intensity = "medium"
    lock_target: bool = True
    fat_tail: bool = True
    memory: bool = True
    jumps: bool = True
    regimes: bool = True


DEFAULT_MODEL = ModelParameters()


@dataclass(frozen=True)
class GeneratorLimits:
    """批量生成时的安全边界与精度限制。"""

    max_count: int = 24_000
    max_fine_steps: int = 8_000_000
    max_attempts: int = 80
    max_price_multiplier: float = 25.0
    price_decimals: int = 8
    max_points_per_candle: int = 8_192


DEFAULT_LIMITS = GeneratorLimits()


@dataclass(frozen=True)
class GeneratedCandle:
    """由 ``generate_candles`` 产出的单根 K 线及其压缩盘中路径。"""

    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    points: tuple[ExecutionPoint, ...]
    minimum_price: float
    maximum_price: float
    parameters: ModelParameters


@dataclass(frozen=True)
class SimulatedBar:
    """流式模拟单根 K 线（或隔夜跳空区间）得到的 OHLC 结果。"""

    open: float
    high: float
    low: float
    close: float


def _js_round_positive(value: float) -> int:
    """模拟 JavaScript ``Math.round`` 对非负数的行为（半值向正无穷舍入）。"""
    return math.floor(value + 0.5)


def _round_scale(value: float, scale_factor: float) -> float:
    return _js_round_positive(value * scale_factor) / scale_factor


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def random_seed() -> int:
    """生成密码学安全的无符号 32 位整型种子（0 .. 2^32 - 1）。"""
    return secrets.randbits(32)


class Mulberry32:
    """与 CandleBridge ``createMulberry32`` 位级一致的 32 位确定性 PRNG。"""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state: int = seed & _UINT32_MASK

    def __call__(self) -> float:
        s = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        self.state = s
        n = ((s ^ (s >> 15)) * (s | 1)) & 0xFFFFFFFF
        n = (n ^ (n + (((n ^ (n >> 7)) * (n | 61)) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((n ^ (n >> 14)) & 0xFFFFFFFF) / 4294967296.0


def standard_normal(rng: Mulberry32) -> float:
    """与 CandleBridge ``createStandardNormal`` 一致的 Box–Muller 标准正态采样。"""
    u1 = max(1e-12, rng())
    u2 = max(1e-12, rng())
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def sample_student_t(rng: Mulberry32, df: int, heavy_tails: bool = True) -> float:
    """抽取单位方差标准化 Student-t 样本（``df > 2``）。

    即使关闭 ``heavy_tails`` 仍消耗相同数量的随机数，保持随机流位置对齐。
    """
    z = standard_normal(rng)
    chi_square = 0.0
    for _ in range(df):
        g = standard_normal(rng)
        chi_square += g * g
    if not heavy_tails:
        return z
    return (z / math.sqrt(chi_square / df)) * math.sqrt((df - 2) / df)


def base_step_volatility(model: ModelParameters) -> float:
    """单细步基础对数波动率：``(baseVolatility / 100) * intensityScale * sqrt(fineSeconds / 60)``。"""
    level = INTENSITY_SCALE[model.intensity]
    return (model.base_volatility / 100.0) * level * math.sqrt(model.fine_seconds / 60.0)


def validate_model_parameters(model: ModelParameters) -> None:
    """按 CandleBridge 上游约束校验模型参数。"""
    if model.intensity not in INTENSITY_SCALE:
        raise CandleBridgeError("INVALID_PARAMETERS", f"Unsupported intensity: {model.intensity}")
    if not all(
        isinstance(flag, bool) for flag in (model.fat_tail, model.memory, model.jumps, model.regimes, model.lock_target)
    ):
        raise CandleBridgeError("INVALID_PARAMETERS", "Model feature toggles must be booleans.")
    numeric_values = (
        model.seed,
        model.fine_seconds,
        model.df,
        model.decay,
        model.base_volatility,
        model.jump_probability,
        model.jump_minimum,
        model.jump_maximum,
        model.shock,
        model.low_multiplier,
        model.high_multiplier,
        model.trend_multiplier,
        model.state_minimum,
        model.state_maximum,
        model.trend_strength,
    )
    if (
        not all(math.isfinite(val) for val in numeric_values)
        or not isinstance(model.seed, int)
        or isinstance(model.seed, bool)
        or model.seed < 0
        or model.seed > _UINT32_MAX
        or model.fine_seconds not in (1, 5)
        or not isinstance(model.df, int)
        or isinstance(model.df, bool)
        or model.df <= 2
        or model.df > 30
        or model.decay < 0
        or model.decay >= 1
        or model.base_volatility <= 0
        or model.base_volatility > 5
        or model.jump_probability < 0
        or model.jump_probability > 1
        or model.jump_minimum < 0
        or model.jump_maximum < model.jump_minimum
        or model.jump_maximum > 30
        or model.shock < 0
        or model.shock > 2
        or min(model.low_multiplier, model.high_multiplier, model.trend_multiplier) <= 0
        or max(model.low_multiplier, model.high_multiplier, model.trend_multiplier) > 10
        or model.state_minimum <= 0
        or model.state_maximum < model.state_minimum
        or model.state_maximum > 43_200
        or model.trend_strength < 0
        or model.trend_strength > 1
    ):
        raise CandleBridgeError("INVALID_PARAMETERS", "One or more stochastic model parameters are out of range.")


def validate_limits(limits: GeneratorLimits) -> None:
    if (
        not isinstance(limits.max_count, int)
        or limits.max_count < 1
        or not isinstance(limits.max_fine_steps, int)
        or limits.max_fine_steps < 1
        or not isinstance(limits.max_attempts, int)
        or limits.max_attempts < 1
        or not isinstance(limits.price_decimals, int)
        or limits.price_decimals < 0
        or limits.price_decimals > 12
        or not isinstance(limits.max_points_per_candle, int)
        or limits.max_points_per_candle < 4
        or not (limits.max_price_multiplier > 1)
    ):
        raise CandleBridgeError("INVALID_PARAMETERS", "Invalid generator limit configuration.")


_DAILY_DF_CHOICES: tuple[int, ...] = (4, 5, 6, 8, 10)
_DAILY_MODEL_FIELDS: tuple[str, ...] = (
    "intensity",
    "base_volatility",
    "df",
    "decay",
    "shock",
    "jump_probability",
    "jump_minimum",
    "jump_maximum",
    "low_multiplier",
    "high_multiplier",
    "trend_multiplier",
    "state_minimum",
    "state_maximum",
    "trend_strength",
)


def _model_to_overrides(model: ModelParameters) -> dict[str, object]:
    return {field: getattr(model, field) for field in _DAILY_MODEL_FIELDS}


def _model_from_overrides(data: object) -> Optional[ModelParameters]:
    if not isinstance(data, dict):
        return None
    kwargs: dict[str, object] = {}
    for field in _DAILY_MODEL_FIELDS:
        if field not in data:
            return None
        kwargs[field] = data[field]
    try:
        model = ModelParameters(
            intensity=kwargs["intensity"],  # type: ignore[arg-type]
            base_volatility=float(kwargs["base_volatility"]),  # type: ignore[arg-type]
            df=kwargs["df"],  # type: ignore[arg-type]
            decay=float(kwargs["decay"]),  # type: ignore[arg-type]
            shock=float(kwargs["shock"]),  # type: ignore[arg-type]
            jump_probability=float(kwargs["jump_probability"]),  # type: ignore[arg-type]
            jump_minimum=float(kwargs["jump_minimum"]),  # type: ignore[arg-type]
            jump_maximum=float(kwargs["jump_maximum"]),  # type: ignore[arg-type]
            low_multiplier=float(kwargs["low_multiplier"]),  # type: ignore[arg-type]
            high_multiplier=float(kwargs["high_multiplier"]),  # type: ignore[arg-type]
            trend_multiplier=float(kwargs["trend_multiplier"]),  # type: ignore[arg-type]
            state_minimum=float(kwargs["state_minimum"]),  # type: ignore[arg-type]
            state_maximum=float(kwargs["state_maximum"]),  # type: ignore[arg-type]
            trend_strength=float(kwargs["trend_strength"]),  # type: ignore[arg-type]
            lock_target=False,
        )
        validate_model_parameters(model)
    except (TypeError, ValueError, CandleBridgeError):
        return None
    return model


@dataclass
class PathState:
    """CandleBridge 随机过程的完整马尔可夫状态，可序列化落库实现断点续算。"""

    rng_state: int
    volatility: float
    regime: int = 0
    remaining: int = 0
    direction: int = 1
    daily_model: Optional[ModelParameters] = None

    @classmethod
    def create(cls, model: ModelParameters = DEFAULT_MODEL, seed: Optional[int] = None) -> PathState:
        validate_model_parameters(model)
        actual_seed = random_seed() if seed is None else seed
        return cls(
            rng_state=actual_seed & _UINT32_MASK,
            volatility=base_step_volatility(model),
            regime=0,
            remaining=0,
            direction=1,
            daily_model=None,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "rng_state": self.rng_state,
            "volatility": self.volatility,
            "regime": self.regime,
            "remaining": self.remaining,
            "direction": self.direction,
        }
        if self.daily_model is not None:
            payload["model"] = _model_to_overrides(self.daily_model)
        return payload

    @classmethod
    def from_dict(cls, data: object) -> Optional[PathState]:
        if not isinstance(data, dict):
            return None
        rng_state = data.get("rng_state")
        volatility = data.get("volatility")
        regime = data.get("regime")
        remaining = data.get("remaining")
        direction = data.get("direction")
        if (
            not isinstance(rng_state, int)
            or isinstance(rng_state, bool)
            or not (0 <= rng_state <= _UINT32_MAX)
            or not isinstance(volatility, (int, float))
            or isinstance(volatility, bool)
            or not math.isfinite(volatility)
            or volatility <= 0
            or not isinstance(regime, int)
            or isinstance(regime, bool)
            or regime not in (0, 1, 2)
            or not isinstance(remaining, int)
            or isinstance(remaining, bool)
            or remaining < 0
            or not isinstance(direction, int)
            or isinstance(direction, bool)
            or direction not in (-1, 1)
        ):
            return None
        daily_model: Optional[ModelParameters] = None
        if "model" in data and data["model"] is not None:
            daily_model = _model_from_overrides(data["model"])
            if daily_model is None:
                return None
        return cls(
            rng_state=rng_state,
            volatility=float(volatility),
            regime=regime,
            remaining=remaining,
            direction=direction,
            daily_model=daily_model,
        )


def sample_daily_model(state: PathState, base: ModelParameters = DEFAULT_MODEL) -> ModelParameters:
    """使用 ``state`` 的确定性随机流为当日抽取一组差异化的 CandleBridge 模型参数。

    以 ``base.base_volatility`` 为基准按比例浮动，并在合法区间内随机抽取波动强度、
    肥尾自由度、波动聚类/冲击系数、跳跃频率与幅度、三态倍率与持续时长及趋势强度，
    使每个交易日呈现不同的市场性格（平静盘整 / 活跃震荡 / 趋势突破 / 事件跳跃）。
    """
    validate_model_parameters(base)
    rng = Mulberry32(state.rng_state)

    def uniform(low: float, high: float) -> float:
        return low + rng() * (high - low)

    pick = rng()
    intensity: Intensity = "low" if pick < 0.20 else ("medium" if pick < 0.70 else "high")
    df = _DAILY_DF_CHOICES[int(rng() * len(_DAILY_DF_CHOICES))]
    state_minimum = round(uniform(15.0, 40.0), 2)
    state_maximum = round(max(state_minimum + 30.0, uniform(90.0, 240.0)), 2)
    jump_minimum = round(uniform(0.3, 0.6), 4)
    jump_maximum = round(max(jump_minimum + 0.5, uniform(1.4, 3.2)), 4)
    base_volatility = round(_clamp(base.base_volatility * uniform(0.75, 1.55), 0.01, 5.0), 6)

    sampled = replace(
        base,
        intensity=intensity,
        base_volatility=base_volatility,
        df=df,
        decay=round(uniform(0.82, 0.95), 4),
        shock=round(uniform(0.25, 0.65), 4),
        jump_probability=round(uniform(0.01, 0.08), 5),
        jump_minimum=jump_minimum,
        jump_maximum=jump_maximum,
        low_multiplier=round(uniform(0.4, 0.7), 4),
        high_multiplier=round(uniform(1.8, 2.8), 4),
        trend_multiplier=round(uniform(0.95, 1.35), 4),
        state_minimum=state_minimum,
        state_maximum=state_maximum,
        trend_strength=round(uniform(0.005, 0.018), 6),
        lock_target=False,
    )
    validate_model_parameters(sampled)
    state.rng_state = rng.state
    return sampled


def sample_gap_minutes(state: PathState, base_minutes: int) -> int:
    """围绕 ``base_minutes`` 随机抽取当日隔夜跳空等效演进时长（0.5x ~ 3.5x）。"""
    if base_minutes <= 0:
        return 0
    rng = Mulberry32(state.rng_state)
    factor = 0.5 + rng() * 3.0
    state.rng_state = rng.state
    return max(5, _js_round_positive(base_minutes * factor))


def _sample_fine_returns(
    state: PathState,
    steps: int,
    model: ModelParameters,
) -> tuple[list[float], float]:
    """从 ``state`` 向前推演 ``steps`` 个细步，原地更新 ``state`` 并返回 ``(returns, sum)``。"""
    s = state.rng_state & 0xFFFFFFFF
    base_vol = base_step_volatility(model)
    regime_multipliers = (model.low_multiplier, model.high_multiplier, model.trend_multiplier)
    jump_threshold = ((model.jump_probability / 100.0) * model.fine_seconds) / 60.0
    trend_drift_step = ((model.trend_strength / 100.0) * model.fine_seconds) / 60.0
    shock = model.shock
    shock_half_var = (shock * shock) / 2.0
    decay = model.decay
    one_minus_decay = 1.0 - decay
    state_min = model.state_minimum
    state_span = model.state_maximum - state_min
    jump_min = model.jump_minimum
    jump_span = model.jump_maximum - jump_min
    minute_to_steps = 60.0 / model.fine_seconds
    df = model.df
    t_scale = math.sqrt((df - 2) / df)
    use_regimes = model.regimes
    use_memory = model.memory
    use_fat_tail = model.fat_tail
    use_jumps = model.jumps

    sqrt = math.sqrt
    log = math.log
    cos = math.cos
    exp = math.exp
    floor = math.floor
    two_pi = 2.0 * math.pi

    def next_u() -> float:
        nonlocal s
        s = (s + 0x6D2B79F5) & 0xFFFFFFFF
        n = ((s ^ (s >> 15)) * (s | 1)) & 0xFFFFFFFF
        n = (n ^ (n + (((n ^ (n >> 7)) * (n | 61)) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((n ^ (n >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def next_normal() -> float:
        u1 = next_u()
        if u1 < 1e-12:
            u1 = 1e-12
        u2 = next_u()
        if u2 < 1e-12:
            u2 = 1e-12
        return sqrt(-2.0 * log(u1)) * cos(two_pi * u2)

    volatility = state.volatility
    regime = state.regime
    remaining = state.remaining
    direction = state.direction
    returns: list[float] = [0.0] * steps
    return_sum = 0.0
    df_range = range(df)

    for i in range(steps):
        if remaining <= 0:
            pick = next_u()
            regime = 0 if pick < 0.52 else (1 if pick < 0.8 else 2)
            remaining = floor((state_min + next_u() * state_span) * minute_to_steps + 0.5)
            direction = -1 if next_u() < 0.5 else 1
        remaining -= 1

        multiplier = regime_multipliers[regime] if use_regimes else 1.0
        vol_shock = base_vol * multiplier * exp(shock * next_normal() - shock_half_var)
        volatility = decay * volatility + one_minus_decay * vol_shock if use_memory else vol_shock

        z = next_normal()
        chi_square = 0.0
        for _ in df_range:
            g = next_normal()
            chi_square += g * g
        epsilon = (z / sqrt(chi_square / df)) * t_scale if use_fat_tail else z

        jump_coin = next_u()
        jump_sign = -1 if next_u() < 0.5 else 1
        jump_size = (jump_min + next_u() * jump_span) / 100.0
        jump = jump_sign * jump_size if (use_jumps and jump_coin < jump_threshold) else 0.0

        drift = direction * trend_drift_step if (use_regimes and regime == 2) else 0.0
        step_return = volatility * epsilon + jump + drift
        returns[i] = step_return
        return_sum += step_return

    state.rng_state = s
    state.volatility = volatility
    state.regime = regime
    state.remaining = remaining
    state.direction = direction
    return returns, return_sum


def simulate_bar(
    state: PathState,
    start_price: float,
    duration_seconds: int,
    model: ModelParameters = DEFAULT_MODEL,
    *,
    price_floor: float = 0.01,
    price_decimals: int = 6,
) -> SimulatedBar:
    """按 CandleBridge 细步随机过程向前模拟 ``duration_seconds`` 秒并聚合为单根 OHLC。

    Args:
        state: 持久化的 ``PathState``，调用后会被原地更新至区间末尾。
        start_price: 区间起始价（如当前市价，包含玩家买卖冲击后的价格）。
        duration_seconds: 模拟时长（秒），必须为 ``model.fine_seconds`` 的正整数倍。
        model: CandleBridge 随机模型参数。
        price_floor: 最低地板价保护。
        price_decimals: 价格保留小数位。
    """
    validate_model_parameters(model)
    if duration_seconds <= 0 or duration_seconds % model.fine_seconds != 0:
        raise CandleBridgeError(
            "INVALID_INTERVAL",
            f"Duration ({duration_seconds}s) must be a positive multiple of fine_seconds ({model.fine_seconds}s).",
        )
    scale_factor = float(10**price_decimals)
    start = max(price_floor, _round_scale(start_price, scale_factor))
    steps = duration_seconds // model.fine_seconds
    returns, _ = _sample_fine_returns(state, steps, model)

    high = start
    low = start
    cumulative_log = 0.0
    current = start
    for step_return in returns:
        cumulative_log = _clamp(cumulative_log + step_return, -_MAX_LOG_RETURN, _MAX_LOG_RETURN)
        current = max(price_floor, _round_scale(start * math.exp(cumulative_log), scale_factor))
        if current > high:
            high = current
        if current < low:
            low = current

    return SimulatedBar(open=start, high=high, low=low, close=current)


def generate_candles(
    *,
    start_price: float,
    end_price: float,
    count: int,
    interval_seconds: int,
    start_time: int,
    minimum_price: float,
    maximum_price: float,
    intensity: Optional[Intensity] = None,
    seed: Optional[int] = None,
    model: Optional[ModelParameters] = None,
    limits: Optional[GeneratorLimits] = None,
) -> list[GeneratedCandle]:
    """完整复现 CandleBridge ``generateCandles``：批量采样有界路径并聚合为 OHLC K 线。"""
    resolved_limits = limits or DEFAULT_LIMITS
    validate_limits(resolved_limits)
    scale_factor = float(10**resolved_limits.price_decimals)

    base_model = model or DEFAULT_MODEL
    resolved_model = replace(
        base_model,
        intensity=intensity if intensity is not None else base_model.intensity,
        seed=seed if seed is not None else base_model.seed,
    )

    start = _round_scale(start_price, scale_factor)
    end = _round_scale(end_price, scale_factor)
    floor = math.ceil(minimum_price * scale_factor - 1e-6) / scale_factor
    ceiling = math.floor(maximum_price * scale_factor + 1e-6) / scale_factor

    if (
        not all(math.isfinite(val) for val in (start, end, floor, ceiling, start_time, count, interval_seconds))
        or start <= 0
        or floor <= 0
        or floor >= ceiling
        or start < floor
        or start > ceiling
        or (resolved_model.lock_target and (end < floor or end > ceiling))
    ):
        raise CandleBridgeError(
            "INVALID_PRICE_RANGE",
            "Start price (and locked target price) must be positive and lie within [minimum_price, maximum_price].",
        )

    end_time = start_time + count * interval_seconds * 1000
    if (
        not isinstance(start_time, int)
        or isinstance(start_time, bool)
        or abs(start_time) > _MAX_SAFE_TIMESTAMP_MS
        or abs(end_time) > _MAX_SAFE_TIMESTAMP_MS
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
        or count > resolved_limits.max_count
        or not isinstance(interval_seconds, int)
        or isinstance(interval_seconds, bool)
        or interval_seconds < 60
        or interval_seconds > 86_400
        or interval_seconds % 60 != 0
    ):
        raise CandleBridgeError(
            "INVALID_INTERVAL",
            f"Interval must be a whole-minute value in [60, 86400] seconds, and count must be in [1, {resolved_limits.max_count}].",
        )

    if math.isfinite(resolved_limits.max_price_multiplier) and (
        ceiling > start * resolved_limits.max_price_multiplier + 1e-8
    ):
        raise CandleBridgeError(
            "INVALID_PRICE_RANGE",
            f"Maximum price cannot exceed {resolved_limits.max_price_multiplier}x the starting price.",
        )

    validate_model_parameters(resolved_model)

    duration_seconds = count * interval_seconds
    steps = duration_seconds // resolved_model.fine_seconds
    if steps > resolved_limits.max_fine_steps:
        raise CandleBridgeError(
            "PATH_TOO_LONG",
            f"Fine path length ({steps} steps) exceeds limit ({resolved_limits.max_fine_steps}).",
        )

    base_vol = base_step_volatility(resolved_model)
    target_log = math.log(end / start)
    low_log = math.log(floor / start)
    high_log = math.log(ceiling / start)
    rng_state = resolved_model.seed & _UINT32_MASK

    for _attempt in range(resolved_limits.max_attempts):
        attempt_state = PathState(
            rng_state=rng_state,
            volatility=base_vol,
            regime=0,
            remaining=0,
            direction=1,
        )
        returns, return_sum = _sample_fine_returns(attempt_state, steps, resolved_model)
        # 拒绝采样继续消费同一随机流，与上游保持完全一致
        rng_state = attempt_state.rng_state

        bridge_correction = (target_log - return_sum) / steps if resolved_model.lock_target else 0.0
        prices: list[float] = [0.0] * (steps + 1)
        prices[0] = start
        cumulative_log = 0.0
        within_bounds = True

        for i in range(steps):
            cumulative_log += returns[i] + bridge_correction
            if i == steps - 1 and resolved_model.lock_target:
                cumulative_log = target_log
            if (
                not math.isfinite(cumulative_log)
                or cumulative_log < low_log - 1e-12
                or cumulative_log > high_log + 1e-12
            ):
                within_bounds = False
                break
            prices[i + 1] = _clamp(_round_scale(start * math.exp(cumulative_log), scale_factor), floor, ceiling)

        if not within_bounds:
            continue
        if resolved_model.lock_target:
            prices[steps] = end

        candles: list[GeneratedCandle] = []
        steps_per_candle = interval_seconds // resolved_model.fine_seconds
        maximum_points = min(
            resolved_limits.max_points_per_candle,
            max(math.ceil(interval_seconds / 60) * 3 + 2, 1_000_000 // count),
        )
        steps_per_minute = 60 // resolved_model.fine_seconds

        for index in range(count):
            start_idx = index * steps_per_candle
            until_idx = start_idx + steps_per_candle
            selected: set[int] = {start_idx, until_idx}
            maximum = prices[start_idx]
            minimum = prices[start_idx]

            for at in range(start_idx, until_idx, steps_per_minute):
                stop = min(until_idx, at + steps_per_minute)
                highest_idx = at
                lowest_idx = at
                for j in range(at, stop + 1):
                    if prices[j] > prices[highest_idx]:
                        highest_idx = j
                    if prices[j] < prices[lowest_idx]:
                        lowest_idx = j
                selected.add(at)
                selected.add(highest_idx)
                selected.add(lowest_idx)
                selected.add(stop)
                if prices[highest_idx] > maximum:
                    maximum = prices[highest_idx]
                if prices[lowest_idx] < minimum:
                    minimum = prices[lowest_idx]

            if len(selected) > resolved_limits.max_points_per_candle:
                raise CandleBridgeError(
                    "INVALID_PARAMETERS",
                    "Point budget is too small to retain minute OHLC. Increase max_points_per_candle.",
                )
            remaining_budget = max(1, maximum_points - len(selected) - 1)
            stride = max(1, math.ceil(steps_per_candle / remaining_budget))
            selected.update(range(start_idx, until_idx, stride))

            points: tuple[ExecutionPoint, ...] = tuple(
                ((j - start_idx) * resolved_model.fine_seconds * 1000, prices[j]) for j in sorted(selected)
            )
            candles.append(
                GeneratedCandle(
                    open_time=start_time + index * interval_seconds * 1000,
                    close_time=start_time + (index + 1) * interval_seconds * 1000,
                    open=prices[start_idx],
                    high=maximum,
                    low=minimum,
                    close=prices[until_idx],
                    points=points,
                    minimum_price=floor,
                    maximum_price=ceiling,
                    parameters=resolved_model,
                ),
            )

        return candles

    raise CandleBridgeError(
        "GENERATION_FAILED",
        f"Unable to sample a path staying within [{floor}, {ceiling}] after {resolved_limits.max_attempts} attempts.",
    )
