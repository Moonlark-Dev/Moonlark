import random

from ...types import GeneratorData, QuestionData
from .levels import l1, l2, l3, l4

GENERATOR_LIST: dict[int, GeneratorData] = {
    1: {"limit_in_second": 7, "max_point": 10, "function": l1.generate_question},
    2: {"limit_in_second": 12, "max_point": 20, "function": l2.generate_question},
    3: {"limit_in_second": 15, "max_point": 30, "function": l3.generate_question},
    4: {"limit_in_second": 17, "max_point": 40, "function": l4.generate_question}
}


async def generate_question(user_id: str, max_level: int) -> QuestionData:
    level = random.randint(1, max_level)
    question = await GENERATOR_LIST[level]["function"](user_id)
    return {
        "question": question,
        "max_point": GENERATOR_LIST[level]["max_point"],
        "level": level,
        "limit_in_sec": GENERATOR_LIST[level]["limit_in_second"]
    }

def get_max_level() -> int:
    return len(GENERATOR_LIST.keys())
