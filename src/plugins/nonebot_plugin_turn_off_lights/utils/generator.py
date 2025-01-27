import random
import math

from .executor import change_light_stats


def create_empty_map(width: int, height: int) -> list[list[bool]]:
    return [[False for _ in range(width)] for _ in range(height)]


def generate_map(width: int, height: int) -> list[list[bool]]:
    game_map = create_empty_map(width, height)
    c = round(math.sqrt(width * height))
    for _ in range(random.randint(c, c + 2)):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        game_map = change_light_stats(game_map, x, y)
    return game_map
