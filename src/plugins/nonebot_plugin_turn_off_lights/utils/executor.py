
def force_update_light_stat(game_map: list[list[bool]], x: int, y: int) -> list[list[bool]]:
    try:
        game_map[y][x] = not game_map[y][x]
    except IndexError:
        pass
    return game_map


def change_light_stats(game_map: list[list[bool]], x: int, y: int) -> list[list[bool]]:
    for _x, _y in [(x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
        game_map = force_update_light_stat(game_map, _x, _y)
    return game_map
