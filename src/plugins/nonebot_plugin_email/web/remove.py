from typing import cast
from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app

from ..utils.remove import remove_email
from ..config import config
from ..config import config
from ...nonebot_plugin_larkuid.session import get_user_id

app = cast(FastAPI, get_app())


@app.delete("/api/emails/{email_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
async def _(request: Request, email_id: int, user_id: str = get_user_id()) -> None:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    await remove_email(email_id)
