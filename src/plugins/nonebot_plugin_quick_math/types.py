from typing import Awaitable, Callable, TypedDict


class Question(TypedDict):
    question: str
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
