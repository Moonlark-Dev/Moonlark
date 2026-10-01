"""TypeSafe System One（Jev）的类型化问题与答案模型

Jev 不生成文本：调用方提交一份 ``state`` 与若干带类型的问题（Choice / Score / Noul），
返回的是可以直接参与代码分支的类型化答案（外加 probabilities 与 confidence）。

问题的 ``instructions`` 与 ``criteria`` 支持 :class:`LangRef`，即一条 LarkLang 键引用，
真正发起请求前由 ``nonebot_plugin_jev`` 解析成本地化文本（与本仓库其它插件一致，
提示词统一放在 ``src/lang/<lang>/jev.yaml``）。
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

QuestionType = Literal["noul", "choice", "score"]


@dataclass(frozen=True)
class LangRef:
    """一条待解析的本地化文本引用：``lang.text(key, lang_str, *args)``"""

    key: str
    args: tuple = ()


def lang_ref(key: str, *args: Any) -> LangRef:
    """构造 :class:`LangRef` 的便捷函数"""
    return LangRef(key=key, args=tuple(args))


TextLike = Union[str, LangRef]
# instructions 允许是结构化对象（问题本体 + 它引用的数据字段）
InstructionsLike = Union[TextLike, dict]
# choice 的 criteria 是 key -> 描述；score 是有序的等级描述列表；noul 是可选的是/否说明
CriteriaLike = Union[dict, list, type(None)]


@dataclass
class Question:
    """一个带类型的问题"""

    type: QuestionType
    instructions: InstructionsLike
    criteria: CriteriaLike = None


def noul(instructions: InstructionsLike, criteria: Optional[TextLike] = None) -> Question:
    """是非题：返回 0-1 之间的概率（noul），适合「是否……」类判断"""
    return Question(type="noul", instructions=instructions, criteria=criteria)


def choice(instructions: InstructionsLike, criteria: dict) -> Question:
    """选择题：从固定选项中选一个，返回 choice / probabilities / confidence"""
    return Question(type="choice", instructions=instructions, criteria=criteria)


def score(instructions: InstructionsLike, criteria: list) -> Question:
    """评分题：在有序的等级谱上打分，返回 score / probabilities / confidence"""
    return Question(type="score", instructions=instructions, criteria=criteria)


class ChoiceAnswer(BaseModel):
    choice: str
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0


class ScoreAnswer(BaseModel):
    score: float
    # 各等级的概率；上游可能返回数组或按等级键控的对象，这里不做严格约束
    probabilities: Any = None
    confidence: float = 0.0

    @property
    def level(self) -> int:
        """按四舍五入落到最近的等级下标上（调用方以等级数为上界再夹一次）"""
        return int(round(self.score))


class NoulAnswer(BaseModel):
    noul: float


Answer = Union[ChoiceAnswer, ScoreAnswer, NoulAnswer]
