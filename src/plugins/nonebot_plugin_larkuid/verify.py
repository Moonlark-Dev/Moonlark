import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html
from nonebot_plugin_orm import get_session
from sqlalchemy.exc import NoResultFound
from .model import SessionData
from .session import create_session, get_user_id
from .lang import lang
from nonebot.log import logger


async def remove_session(session_id: str) -> None:
    await asyncio.sleep(180)
    async with get_session() as session:
        try:
            data = await session.get_one(
                SessionData,
                session_id
            )
        except NoResultFound:
            return
        if data.activate_code is not None:
            await session.delete(data)


@get_app().get("/user/login/verify")
async def _(request: Request, response: Response, uid: str, sessionSaveTime: int = 1):
    session_id, activate_code = await create_session(
        uid,
        request.headers["User-Agent"],      # 禁止不发送 User-Agent 的客户端登陆
        sessionSaveTime
    )
    logger.info(f"已创建 Session: {session_id} ({request.headers['User-Agent']=})")
    response = PlainTextResponse(
        await template_to_html(
            Path(__file__).parent.joinpath("template").as_posix(),
            "verify.html.jinja",
            title=await lang.text("verify.title", uid),
            tip=await lang.text("verify.tip", uid, uid),
            cmd=await lang.text("verify.cmd", uid, activate_code),
            uid=uid,
            ok=await lang.text("verify.ok", uid),
            cancel=await lang.text("verify.cancel", uid),
            cookie=await lang.text("verify.cookie", uid),
        ),
        media_type="text/html"
    )
    response.set_cookie(
        "session_id",
        session_id,
        expires=(datetime.now(timezone.utc) + timedelta(days=sessionSaveTime))
    )
    asyncio.create_task(remove_session(session_id))
    return response


@get_app().get("/api/is_logged_in")
async def _(request: Request, user_id: Optional[str] = get_user_id()):
    return {"logged": user_id is not None}
