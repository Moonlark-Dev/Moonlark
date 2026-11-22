"""海龟汤的数据结构：谜题、问答历史与判定结果。"""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, field_validator

PuzzleId = Union[int, str]


class Puzzle(BaseModel):
    """一道海龟汤谜题。

    字段与上游 ``nonebot-plugin-ai-turtle-soup`` 的题库格式保持一致：
    ``id`` 可选，其余三项必填，``supplementary_info`` 是主持人的事实依据，
    同时也按顺序作为游戏内提示。
    """

    id: Optional[PuzzleId] = None
    title: str
    puzzle_setting: str
    supplementary_info: list[str]
    solution: str

    @field_validator("title", "puzzle_setting", "solution")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("谜题字段不能为空")
        return value

    @field_validator("supplementary_info")
    @classmethod
    def _non_empty_list(cls, value: list[str]) -> list[str]:
        hints = [hint.strip() for hint in value if hint and hint.strip()]
        if not hints:
            raise ValueError("谜题的附加信息不能为空")
        return hints


class HistoryItem(BaseModel):
    """一条问答记录。"""

    user_id: str
    question: str
    reply: str
    percent: int


class JudgeResult(BaseModel):
    """一次判定的结果。``reply`` 是给玩家看的简短回答（是 / 不是 / 不重要）。"""

    reply: str
    percent: int
    solved: bool = False


class LLMJudgeResponse(BaseModel):
    """LLM 判定模式的 JSON 响应（见 ``src/prompt/turtle_soup/judge.md.jinja``）。"""

    percent: int
    reply: str = ""

    @field_validator("percent")
    @classmethod
    def _clamp_percent(cls, value: int) -> int:
        return max(0, min(100, value))


class ProgressResponse(BaseModel):
    """LLM 重算进度模式的 JSON 响应。"""

    recalculated_percent: int

    @field_validator("recalculated_percent")
    @classmethod
    def _clamp_percent(cls, value: int) -> int:
        return max(0, min(100, value))


JudgeBackend = Literal["decision", "llm"]


class AskOutcome(BaseModel):
    """提问之后的结果，供指令层渲染消息。"""

    question: str
    reply: str
    percent: int
    asked: int
    solved: bool
    title: str = ""
    puzzle_setting: str = ""
    solution: str = ""
    supplementary_info: list[str] = []


class HintOutcome(BaseModel):
    """获取提示的结果。"""

    hint: str = ""
    current: int = 0
    total: int = 0
    finished: bool = False


class EndOutcome(BaseModel):
    """一局游戏结束时的最终数据。"""

    solved: bool
    percent: int
    asked: int
    title: str
    puzzle_setting: str
    solution: str
    supplementary_info: list[str]
    solved_by: str = ""
