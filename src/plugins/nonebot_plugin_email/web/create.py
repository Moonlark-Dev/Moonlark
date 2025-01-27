from typing import cast
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from nonebot import get_app

from ..models import EmailDataArgs
from ..utils.send import send_email, send_global_email
from ..config import config
from nonebot_plugin_larkuid.session import get_user_id

app = cast(FastAPI, get_app())


@app.post("/api/emails/create")
async def _(request: Request, args: EmailDataArgs, user_id: str = get_user_id()) -> JSONResponse:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if args.receivers == "*":
        email_id = await send_global_email(args.subject, args.content, args.sender, args.items)
    else:
        email_id = await send_email(args.receivers, args.subject, args.content, args.sender, args.items)
    return JSONResponse(
        {"email_id": email_id}, status_code=status.HTTP_201_CREATED, headers={"Location": f"/api/emails/{email_id}"}
    )
