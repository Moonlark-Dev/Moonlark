def get_level_by_experience(exp: int) -> int:
    level = 0
    while True:
        if level ** 3 >= exp:
            return level
        level += 1