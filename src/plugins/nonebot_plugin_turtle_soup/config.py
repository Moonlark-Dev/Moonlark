from typing import Literal

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """海龟汤的玩法参数。"""

    # 每局最多提问次数；用完后只能放弃或等本局超时
    turtle_soup_max_questions: int = 50
    # 本局作答期限（秒），默认 36 小时；过期静默结束，不发送任何提示
    turtle_soup_timeout: int = 36 * 60 * 60
    # 判定方式：decision 走 Decisions API（默认），llm 走 OpenAI 兼容接口
    # 未配置 DECISION_API_KEY 时即使填 decision 也会自动退回 LLM
    turtle_soup_judge_mode: Literal["decision", "llm"] = "decision"
    # LLM 出题 / 判定 / 重算进度的超时（秒）
    turtle_soup_generate_timeout: int = 180
    turtle_soup_judge_timeout: int = 120
    # Decisions API 单次请求的超时（秒），避免卡住整局游戏
    turtle_soup_decision_timeout: float = 20.0
    # Decisions API 判定「玩家已说出汤底」的概率阈值
    turtle_soup_solved_threshold: float = 0.6
    # Decisions API 判定的最低置信度：低于该值（或判定缺少有效答案时）退回 LLM 判定
    turtle_soup_decision_min_confidence: float = 0.5
    # 开一局扣除的 VimCoin（向发起者收取，出题失败时原额退回）
    turtle_soup_generate_cost: float = 10.0
    # 每获取一条提示扣除的 VimCoin（向要提示的人收取）
    turtle_soup_hint_cost: float = 2.0
    # 解开本局奖励给解出者的 VimCoin
    turtle_soup_reward: float = 20.0


config = get_plugin_config(Config)
