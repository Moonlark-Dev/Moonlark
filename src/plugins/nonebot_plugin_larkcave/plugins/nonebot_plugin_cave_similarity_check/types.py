from typing import Literal, TypedDict

from ...model import CaveData


class CheckPassedResult(TypedDict):
    passed: Literal[True]

class CheckFailedResult(TypedDict):
    passed: Literal[False]
    similar_cave: CaveData
    similarity: float

CheckResult = CheckFailedResult | CheckPassedResult


