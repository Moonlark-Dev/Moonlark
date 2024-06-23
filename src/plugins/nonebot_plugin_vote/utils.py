from datetime import datetime
from typing import AsyncGenerator, Optional
from nonebot_plugin_alconna import Match
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from ..nonebot_plugin_render.render import render_template

from ..nonebot_plugin_larkuser.utils.user import get_user
from ..nonebot_plugin_larkutils import get_group_id, get_id
from .lang import lang
from .model import Choice, Vote, VoteLog
from .typing import ChoiceData


async def create_vote(
    title: str,
    sponsor: str,
    content: str,
    choices: list[str],
    session: async_scoped_session,
    end_time: datetime,
    group: Optional[str] = None,
) -> int:
    vote_id = await get_id(session, Vote.id)
    session.add(Vote(id=vote_id, title=title, content=content, sponsor=sponsor, end_time=end_time, group=group))
    _id = 0
    for choice in choices:
        _id += 1
        session.add(Choice(id=_id, belong=vote_id, text=choice))
    await session.commit()
    return vote_id


def is_vote_open(vote: Vote) -> bool:
    return (vote.end_time - datetime.now()).total_seconds() > 0


async def get_vote_data(
    session: async_scoped_session, vote_id: Match[int], group_id: str = get_group_id()
) -> Optional[Vote]:
    if not vote_id.available:
        return None
    try:
        vote = await session.get_one(Vote, {"id": vote_id.result})
    except NoResultFound:
        return None
    if vote.group in [None, group_id]:
        return vote
    return None


def get_percent(count: int, total_count: int) -> int:
    try:
        return round(count / total_count * 100)
    except ZeroDivisionError:
        return 0


async def get_choice(total_count: int, vote_data: Vote, session: async_scoped_session) -> list[ChoiceData]:
    choice_list: list[ChoiceData] = [
        {
            "id": choice.id,
            "text": choice.text,
            "count": (
                count := len(
                    (
                        await session.scalars(
                            select(VoteLog).where(VoteLog.belong == vote_data.id).where(VoteLog.choice == choice.id)
                        )
                    ).all()
                )
            ),
            "percent": get_percent(count, total_count),
        }
        for choice in (await session.scalars(select(Choice).where(Choice.belong == vote_data.id))).all()
    ]
    return sorted(choice_list, key=lambda x: x["id"])


async def is_user_voted(vote_data: Vote, user_id: str, session: async_scoped_session) -> bool:
    return (
        await session.scalar(select(VoteLog).where(VoteLog.belong == vote_data.id).where(VoteLog.user_id == user_id))
    ) is not None


async def get_choice_content(vote_data: Vote, choice_id: int, session: async_scoped_session) -> None | str:
    data = await session.scalar(select(Choice).where(Choice.belong == vote_data.id).where(Choice.id == choice_id))
    if data is None:
        return
    return data.text


async def generate_vote_image(user_id: str, session: async_scoped_session, vote_data: Vote) -> bytes:
    total_count = len((await session.scalars(select(VoteLog).where(VoteLog.belong == vote_data.id))).all())
    return await render_template(
        "vote.html.jinja",
        await lang.text("vote_image.page_title", user_id),
        user_id,
        {
            "open": is_vote_open(vote_data),
            "status": {
                "open": await lang.text("status.open", user_id),
                "closed": await lang.text("status.closed", user_id),
            },
            "id": await lang.text("vote_image.id", user_id, vote_data.id),
            "choice_text": await lang.text("vote_image.choice_text", user_id),
            "title": vote_data.title,
            "content": vote_data.content,
            "choices": await get_choice(total_count, vote_data, session),
            "sponsor": await lang.text("vote_image.sponsor", user_id, (await get_user(vote_data.sponsor)).nickname),
            "end_time": await lang.text(
                "vote_image.end_time", user_id, vote_data.end_time.strftime("%Y-%m-%d %H:%M:%S")
            ),
        },
    )


async def get_vote_list(
    show_all: bool, group_id: str, session: async_scoped_session
) -> AsyncGenerator[tuple[Vote, bool], None]:
    for vote in (await session.scalars(select(Vote))).all():
        if vote.group not in [group_id, None]:
            continue
        if (status := is_vote_open(vote)) or show_all:
            yield vote, status


async def generate_vote_list(
    user_id: str, group_id: str, session: async_scoped_session, show_all: bool = False
) -> bytes:
    return await render_template(
        "vote_list.html.jinja",
        await lang.text("list.title", user_id),
        user_id,
        {
            "vote_list": [
                {
                    "id": vote.id,
                    "title": vote.title,
                    "status": await lang.text("status.open" if is_open else "status.closed", user_id),
                }
                async for vote, is_open in get_vote_list(show_all, group_id, session)
            ],
        },
    )
