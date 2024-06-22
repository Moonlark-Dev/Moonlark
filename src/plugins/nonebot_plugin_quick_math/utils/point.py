from ..types import QuestionData
from datetime import datetime


def get_point(question: QuestionData, start_time: datetime) -> int:
    used_time = (datetime.now() - start_time).total_seconds()
    return round(question["max_point"] / question["limit_in_sec"] * max(question["limit_in_sec"] - used_time, 1))
