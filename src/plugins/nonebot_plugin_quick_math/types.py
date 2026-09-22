from enum import Enum
from typing import Awaitable, Callable, Literal
from typing_extensions import TypedDict


class Question(TypedDict):
    question: str
    options: list[str]
    # 正确选项对应的字母（A/B/C/D…）。所有题目都是选择题，判题直接比较字母，
    # 不再解析用户输入或调用 AI 判定答案文本。
    answer: str


class QuestionData(TypedDict):
    question: Question
    max_point: int
    level: int
    limit_in_sec: int


GENERATOR_FUNCTION = Callable[[str], Awaitable[Question]]


class GeneratorData(TypedDict):
    limit_in_second: int
    max_point: int
    function: GENERATOR_FUNCTION


class JsonCycleData(TypedDict):
    number: int
    start_time: int


LEVEL = Literal["A", "B", "C", "D"]


class ReplyType(Enum):
    RIGHT = 0
    TIMEOUT = 1
    WRONG = 2
    SKIP = 3


class ExtendReplyType(Enum):
    LEAVE = 4


LevelModeString = Literal["random", "lock"]
LevelMode = tuple[LevelModeString, int]
