import random
import traceback
from nonebot.log import logger

from ...types import GeneratorData, QuestionData
from .levels import l1, l2, l3, l4, l5, l6, l7

GENERATOR_LIST: dict[int, GeneratorData] = {
    1: {"limit_in_second": 7, "max_point": 10, "function": l1.generate_question},
    2: {"limit_in_second": 12, "max_point": 20, "function": l2.generate_question},
    3: {"limit_in_second": 15, "max_point": 30, "function": l3.generate_question},
    4: {"limit_in_second": 17, "max_point": 40, "function": l4.generate_question},
    5: {"limit_in_second": 42, "max_point": 50, "function": l5.generate_question},
    6: {"limit_in_second": 68, "max_point": 60, "function": l6.generate_question},
    7: {"limit_in_second": 72, "max_point": 70, "function": l7.generate_question},
}


def get_difficulty_list(max_level: int) -> list[int]:
    difficulties = []
    for i in range(max_level):
        level = i + 1
        difficulties.extend([level] * level)
    return difficulties


async def generate_question(user_id: str, level: int) -> QuestionData:
    try:
        question = await GENERATOR_LIST[level]["function"](user_id)
    except Exception:
        logger.warning(f"生成题目时出现错误 ({level=}): {traceback.format_exc()}")
        return await generate_question(user_id, level)
    logger.debug(question)
    return {
        "question": question,
        "max_point": GENERATOR_LIST[level]["max_point"],
        "level": level,
        "limit_in_sec": GENERATOR_LIST[level]["limit_in_second"],
    }


def get_max_level() -> int:
    return len(GENERATOR_LIST.keys())
