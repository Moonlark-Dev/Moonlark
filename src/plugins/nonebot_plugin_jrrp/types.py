from enum import Enum


class LuckType(Enum):
    PERFECT_LUCK = 1  # 100
    ALMOST_PERFECT = 2  # 99
    GREAT_DAY = 3  # 85-98
    GOOD_DAY = 4  # 71-84
    FAIR_DAY = 5  # 57-70
    AVERAGE_DAY = 6  # 43-56
    BELOW_AVERAGE = 7  # 29-42
    POOR_DAY = 8  # 15-28
    BAD_DAY = 9  # 1-14
    TERRIBLE_LUCK = 10  # 0
