from datetime import datetime, timedelta
from typing import Optional

from nonebot import logger
from nonebot.params import ArgPlainText, Depends
from nonebot.typing import T_State
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, Option, Subcommand, UniMessage, on_alconna
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_group_id, get_user_id, is_user_superuser, review_text
from nonebot_plugin_larkutils.extra import parse_exit_input
from .config import config
from .lang import lang
from .modules import Choice, Vote, VoteLog
from .utils import (
    create_vote,
    generate_vote_image,
    generate_vote_list,
    get_choice_content,
    get_vote_data,
    is_user_voted,
    is_vote_open,
)

alc = Alconna(
    "vote",
    Subcommand("create", Option("-g|--global"), Option("-l|--last", Args["hour", int, 2])),
    Subcommand("close"),
    Args["vote_id?", int],
    Args["choice?", int],
    Option("-a|--all"),
)
vote = on_alconna(alc)


@vote.handle()
async def _(
    result: Arparma,
    choice: Match[int],
    hour: Match[int],
    session: async_scoped_session,
    state: T_State,
    user_id: str = get_user_id(),
    is_superuser: bool = is_user_superuser(),
    group_id: str = get_group_id(),
    vote_data: Optional[Vote] = Depends(get_vote_data),
) -> None:
    if result.find("create"):
        state["end_time"] = datetime.now() + timedelta(hours=hour.result if hour.available else config.vote_remain_hour)
        state["private"] = not result.find("create.global")
        await lang.send("create.create_title", user_id)
    elif vote_data is None and result.find("vote_id"):
        await lang.finish("vote.not_found", user_id)
    elif vote_data is None:
        await vote.finish(
            UniMessage().image(raw=await generate_vote_list(user_id, group_id, session, result.find("all")))
        )
    elif choice.available:
        if not is_vote_open(vote_data):
            await lang.finish("choose.vote_ended", user_id)
        if await is_user_voted(vote_data, user_id, session):
            await lang.finish("choose.voted", user_id)
        if (content := await get_choice_content(vote_data, choice.result, session)) is None:
            await lang.finish("choose.choice_not_found", user_id, choice.result)
        session.add(VoteLog(belong=vote_data.id, user_id=user_id, choice=choice.result))
        await session.commit()
        await lang.finish("choose.success", user_id, content)
    elif result.find("close"):
        if vote_data.sponsor == user_id or is_superuser:
            vote_data.end_time = datetime.now()
            await lang.send("close.success", user_id, vote_data.id)
            await session.commit()
            await vote.finish()
        else:
            await lang.finish("vote.no_permission", user_id)
    else:
        await vote.finish(UniMessage().image(raw=await generate_vote_image(user_id, session, vote_data)))


@vote.got("title")
async def _(state: T_State, title: str = ArgPlainText(), user_id: str = get_user_id()) -> None:
    await parse_exit_input(title, user_id)
    state["title"] = title
    await lang.send("create.create_content", user_id)


@vote.got("content")
async def _(state: T_State, content: str = ArgPlainText(), user_id: str = get_user_id()) -> None:
    await parse_exit_input(content, user_id)
    state["content"] = content
    state["choices"] = []
    await lang.send("create.get_choice", user_id, 0)


@vote.got("choice")
async def _(
    state: T_State,
    session: async_scoped_session,
    group_id: str = get_group_id(),
    choice: str = ArgPlainText(),
    user_id: str = get_user_id(),
) -> None:
    await parse_exit_input(choice, user_id)
    if choice.lower() in ["ok", "save", "done"]:
        if len(state["choices"]) < 2:
            await vote.reject(await lang.text("create.need_choice", user_id))
        if not (result := await review_text("\n".join([state["title"], state["content"]] + state["choices"])))[
            "compliance"
        ]:
            await lang.finish("create.review_failed", user_id, result["message"])
        vote_id = await create_vote(
            state["title"],
            user_id,
            state["content"],
            state["choices"],
            session,
            state["end_time"],
            group_id if state["private"] else None,
        )
        await lang.send("create.created", user_id, vote_id)
    elif choice.lower() in ["b", "back"]:
        await vote.reject(prompt=await lang.text("create.choice_deleted", user_id, state["choices"].pop(-1)))
    else:
        state["choices"].append(choice)
        logger.debug(state["choices"])
        await vote.reject(await lang.text("create.get_choice", user_id, len(state["choices"])))
