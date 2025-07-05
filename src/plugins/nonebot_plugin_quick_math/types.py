from enum import Enum
from typing import Awaitable, Callable, Literal, TypedDict


class Question(TypedDict):
    question: str
    answer: Callable[[str], Awaitable[bool]]


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
