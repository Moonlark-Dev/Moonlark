from typing import Awaitable, Callable, TypedDict


class Question(TypedDict):
    question: str
    answer: str

GENERATOR_FUNCTION = Callable[[str], Awaitable[Question]]

class GeneratorData(TypedDict):
    limit_in_second: int
    max_point: int
    function: GENERATOR_FUNCTION
