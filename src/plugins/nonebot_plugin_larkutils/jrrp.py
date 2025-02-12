from datetime import date
from typing import Optional


def str_to_int(s: str) -> int:
    total = 0
    for i, char in enumerate(s):
        total += ord(char) * (256**i)
    return total


def get_luck_value(user_id: str, target_date: Optional[date] = None) -> int:
    d = str(target_date or date.today())
    return str_to_int(f"{d}::{user_id}") % 101
