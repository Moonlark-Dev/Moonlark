from .user import get_user, set_user_data


async def add_fav(user_id: str, count: float) -> None:
    await set_user_data(
        user_id,
        vimcoin=(await get_user(user_id)).favorability + count
    )
