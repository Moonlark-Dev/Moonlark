from datetime import date
import random

def str_to_int(s: str) -> int:
    total = 0
    for i, char in enumerate(s):
        total += ord(char) * (256 ** i)
    return total

def get_luck_value(user_id: str) -> int:
    return str_to_int(f"{date.today()}::{user_id}") % 101
