from .user import get_user, set_user_data


async def add_vimcoin(user_id: str, count: float) -> None:
    await set_user_data(user_id, vimcoin=(await get_user(user_id)).vimcoin + count)


async def use_vimcoin(user_id: str, count: float) -> None:
    await set_user_data(user_id, vimcoin=(await get_user(user_id)).vimcoin - count)


async def has_vimcoin(user_id: str, count: float) -> bool:
    return (await get_user(user_id)).vimcoin >= count
