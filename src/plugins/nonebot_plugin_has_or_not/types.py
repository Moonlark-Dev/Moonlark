"""“有无有无” 的数据结构：题目、生成结果与本地缓存文件格式。"""

from pydantic import BaseModel, Field


class PromptPair(BaseModel):
    """一组词：contain 包含答案特征，missing 不包含答案特征。"""

    contain: str
    missing: str


class GeneratedQuestion(BaseModel):
    """模型生成的一道题。"""

    answer: str
    prompts: list[PromptPair]


class QuestionStoreData(BaseModel):
    """本地缓存文件：待玩题目 + 近期出过的答案与词语组合（用于去重）。"""

    questions: list[GeneratedQuestion] = Field(default_factory=list)
    recent_answers: list[str] = Field(default_factory=list)
    recent_word_sets: list[list[str]] = Field(default_factory=list)
