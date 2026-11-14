"""OpenRouter Decisions API 的类型化问题与答案模型

Decisions API 不生成自由文本：调用方提交一份 ``state``（文本、结构化数据或多模态内容列表）
与若干带类型的问题（Noul / Choice / Score / Box），返回可以直接参与代码分支的类型化答案
（附带 probabilities 与 confidence）。

问题的 ``instructions`` 与 ``criteria`` 支持 :class:`LangRef`，即一条 LarkLang 键引用，
真正发起请求前由 ``nonebot_plugin_decision`` 解析成本地化文本（提示词统一放在
``src/lang/<lang>/decision.yaml``）。
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

QuestionType = Literal["noul", "choice", "score", "box"]


@dataclass(frozen=True, slots=True)
class LangRef:
    """一条待解析的本地化文本引用：``lang.text(key, lang_str, *args)``"""

    key: str
    args: tuple[Any, ...] = ()


def lang_ref(key: str, *args: Any) -> LangRef:
    """构造 :class:`LangRef` 的便捷函数"""
    return LangRef(key=key, args=tuple(args))


TextLike = Union[str, LangRef]
# choice 的 criteria 是 key -> 描述（多模态场景允许为 None）；
# score 是有序的等级描述列表；noul 是可选的 {"true": ..., "false": ...} 说明；box 无 criteria
CriteriaLike = Union[dict[str, Optional[TextLike]], list[TextLike], None]


@dataclass(slots=True)
class Question:
    """一个带类型的决策问题"""

    type: QuestionType
    instructions: TextLike
    criteria: CriteriaLike = None


def noul(
    instructions: TextLike,
    criteria: Optional[dict[str, TextLike]] = None,
    *,
    true: Optional[TextLike] = None,
    false: Optional[TextLike] = None,
) -> Question:
    """是非题：返回 0-1 之间的概率（noul），适合「是否……」类判断"""
    merged: dict[str, Optional[TextLike]] = {}
    if criteria:
        merged.update(criteria)
    if true is not None:
        merged["true"] = true
    if false is not None:
        merged["false"] = false
    return Question(type="noul", instructions=instructions, criteria=merged or None)


def choice(instructions: TextLike, criteria: dict[str, Optional[TextLike]]) -> Question:
    """选择题：从固定选项中选一个，返回 choice / probabilities / confidence"""
    return Question(type="choice", instructions=instructions, criteria=criteria)


def score(instructions: TextLike, criteria: list[TextLike]) -> Question:
    """评分题：在有序的等级谱上打分，返回 score / probabilities / confidence"""
    return Question(type="score", instructions=instructions, criteria=criteria)


def box(instructions: TextLike) -> Question:
    """边界框定位题：在图像 state 中定位目标归一化坐标，返回 box / confidence"""
    return Question(type="box", instructions=instructions, criteria=None)


class ChoiceAnswer(BaseModel):
    choice: str
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0


class ScoreAnswer(BaseModel):
    score: float
    # 各等级的概率；不同上游模型可能返回列表或字典，这里不做严格约束
    probabilities: Any = None
    legend: Optional[dict[str, Any]] = None
    confidence: float = 0.0

    @property
    def level(self) -> int:
        """按四舍五入落到最近的等级下标上（调用方以等级数为上界再夹一次）"""
        return round(self.score)


class NoulAnswer(BaseModel):
    noul: float
    confidence: Optional[float] = None


class BoxCoords(BaseModel):
    top: float
    bottom: float
    left: float
    right: float


class BoxAnswer(BaseModel):
    box: BoxCoords
    confidence: float = 0.0


Answer = Union[ChoiceAnswer, ScoreAnswer, NoulAnswer, BoxAnswer]
