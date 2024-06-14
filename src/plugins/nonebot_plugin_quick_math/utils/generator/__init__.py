import random

from ...types import GeneratorData, Question
from .levels import l1

GENERATOR_LIST: dict[int, GeneratorData] = {
    1: {"limit_in_second": 7, "max_point": 10, "function": l1.generate_question}
}


async def generate_question(user_id: str, max_level: int) -> Question:
    return await GENERATOR_LIST[random.randint(1, max_level)]["function"](user_id)
