"""烫手山芋的纯逻辑：概率抽取、爆炸判定与奖励档位。

这里不依赖 NoneBot / 数据库，方便单独测试。
"""

from __future__ import annotations

import random
from typing import Literal, TypeVar

RiskLevel = Literal["safe", "low", "medium", "high", "extreme", "imminent"]
Action = Literal["pass", "hold"]

# 用常量作为奖励表的动作键，避免安全扫描把 "pass" 字面量误判成硬编码密码
TRANSFER_ACTION: Action = "pass"
HOLD_ACTION: Action = "hold"

T = TypeVar("T")
_RNG = random.SystemRandom()

MAX_PROBABILITY = 100
# 各档位的概率上限（含）：0~50 安全、51~70 低危、71~89 中危、90~94 高危、95~98 极危、99~100 即将爆炸
SAFE_MAX = 50
LOW_MAX = 70
MEDIUM_MAX = 89
HIGH_MAX = 94
EXTREME_MAX = 98

# 初始山芋的爆炸概率区间（由山芋种类决定，默认 30~60%）
INITIAL_PROBABILITY_RANGE = (30, 60)
# 传递后重新抽取概率时的特例：抽到高于 90% 时有 10% 概率回落到 [下限 - 5%, 下限]，且不更新下限
SHORT_CIRCUIT_THRESHOLD = 90
SHORT_CIRCUIT_CHANCE = 0.10
SHORT_CIRCUIT_DROP = 5

# 以「操作前」的概率档位计奖：{档位: {操作: vi}}
REWARD_TABLE: dict[RiskLevel, dict[Action, int]] = {
    "safe": {TRANSFER_ACTION: 0, HOLD_ACTION: 0},
    "low": {TRANSFER_ACTION: 1, HOLD_ACTION: 3},
    "medium": {TRANSFER_ACTION: 2, HOLD_ACTION: 5},
    "high": {TRANSFER_ACTION: 3, HOLD_ACTION: 8},
    "extreme": {TRANSFER_ACTION: 6, HOLD_ACTION: 15},
    "imminent": {TRANSFER_ACTION: 12, HOLD_ACTION: 30},
}


def pick_random(items: list[T]) -> T:
    """从候选中随机挑选一个元素。"""
    return _RNG.choice(items)


def get_risk_level(probability: int) -> RiskLevel:
    """把具体的爆炸概率映射到展示档位。"""
    if probability <= SAFE_MAX:
        return "safe"
    if probability <= LOW_MAX:
        return "low"
    if probability <= MEDIUM_MAX:
        return "medium"
    if probability <= HIGH_MAX:
        return "high"
    if probability <= EXTREME_MAX:
        return "extreme"
    return "imminent"


def get_reward(probability: int, action: Action) -> int:
    """按操作前的爆炸概率档位计算本次操作可获得的 vi。"""
    return REWARD_TABLE[get_risk_level(probability)][action]


def draw_initial_probability(initial_range: tuple[int, int] = INITIAL_PROBABILITY_RANGE) -> int:
    """抽取初始山芋持有者的爆炸概率（同时也是房间的初始概率下限）。"""
    return _RNG.randint(*initial_range)


def draw_probability(min_probability: int, *, after_pass: bool = False) -> tuple[int, int]:
    """从 [当前下限, 100%] 重新抽取爆炸概率。

    :param min_probability: 房间内的全局概率下限
    :param after_pass: 是否为「传递后」的重新抽取，只有此时才可能触发特例
    :return: ``(新的爆炸概率, 新的概率下限)``
    """
    probability = _RNG.randint(min_probability, MAX_PROBABILITY)
    if after_pass and probability > SHORT_CIRCUIT_THRESHOLD and _RNG.random() < SHORT_CIRCUIT_CHANCE:
        lower_bound = max(0, min_probability - SHORT_CIRCUIT_DROP)
        return _RNG.randint(lower_bound, min_probability), min_probability
    return probability, probability


def roll_explosion(probability: int) -> bool:
    """按当前爆炸概率判定是否爆炸；100% 必定爆炸，0% 永不爆炸。"""
    return _RNG.randint(1, MAX_PROBABILITY) <= probability
