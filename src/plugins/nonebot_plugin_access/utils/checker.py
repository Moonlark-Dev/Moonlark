from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher, matchers
from nonebot.message import run_preprocessor
from nonebot.params import Depends
from nonebot_plugin_alconna import MsgTarget, UniMessage
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from nonebot_plugin_larkutils import get_group_id
from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_access.config import config
from nonebot_plugin_access.lang import lang
from nonebot_plugin_access.models import SubjectData


async def get_subject_list(bot: Bot, group_id: str = get_group_id(), user_id: str = get_user_id()) -> list[str]:
    return ["all", f"group_{group_id}", f"bot_{bot.self_id}", user_id]


async def is_available(subject: str, name: str, default: bool = True) -> bool:
    async with get_session() as session:
        result = (
            await session.scalars(
                select(SubjectData.available).where(SubjectData.subject == subject).where(SubjectData.name == name)
            )
        ).all()
        logger.debug(f"权限检查结果 ({subject=}, {name=}): {result}")
        return all(result or [default])


async def send_fallback(event: Event, result: bool, target: MsgTarget) -> None:
    if config.access_fallback and not result:
        await UniMessage().text(await lang.text("access.failed", event.get_user_id())).send(target)


async def check_access(matcher: Matcher, event: Event, subject_list: list[str] = Depends(get_subject_list)) -> bool:
    if event.get_type() != "message":
        return True
    return all(
        [
            all(
                [
                    await is_available(
                        subject,
                        name,
                    )
                    for subject in subject_list
                ]
            )
            for name in [
                "all",
                f"plugin_{matcher.plugin_name}",
            ]
        ]
    )


#
# async def handler(matcher: Matcher, user_id: str = get_user_id(), result: bool = Depends(check_access)) -> None:
#     if config.access_fallback and not result:
#         await UniMessage().text(await lang.text("access.failed", user_id)).send()
#     if not result:
#         await matcher.finish()
#
#
# @get_driver().on_startup
# async def _() -> None:
#     for matcher in matchers.provider[1]:
#         if (not matcher.plugin_name) or matcher.type != "message":
#             continue
#         matcher.handle()(handler)
#         matcher.handlers.insert(0, matcher.handlers.pop(-1))


@run_preprocessor
async def handler(user_id: str = get_user_id(), result: bool = Depends(check_access)) -> None:
    if config.access_fallback and not result:
        await UniMessage().text(await lang.text("access.failed", user_id)).send()
    if not result:
        raise IgnoredException("权限检查不通过")
