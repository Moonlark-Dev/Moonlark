from .user import get_user, set_user_data

def get_level_by_experience(exp: int) -> int:
    level = 0
    while True:
        if level ** 3 >= exp:
            return level
        level += 1

async def add_exp(user_id: str, exp: int) -> None:
    await set_user_data(
        user_id,
        experience=(await get_user(user_id)).experience + exp
    )
