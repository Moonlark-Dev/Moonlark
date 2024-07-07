from .__main__ import lang


class ItemLockedError(Exception):

    async def send_output(self, user_id: str) -> None:
        await lang.finish("exc.locked", user_id)
