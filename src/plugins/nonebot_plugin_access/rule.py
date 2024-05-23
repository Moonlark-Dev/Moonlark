from operator import is_
from nonebot import get_driver, logger
from nonebot.rule import Rule
from nonebot.matcher import matchers
from nonebot_plugin_orm import get_session
from nonebot.adapters import Bot, Event
from sqlalchemy import select
from .model import SubjectData
from ..nonebot_plugin_larkutils import get_group_id
from nonebot.params import Depends


async def get_subject_list(
        bot: Bot,
        event: Event,
        group_id: str = get_group_id()
) -> list[str]:
    subject_list = [
        "all",
        f"group_{group_id}",
        f"bot_{bot.self_id}"
    ]
    try:
        subject_list.append(event.get_user_id())
    except ValueError:
        pass
    return subject_list


async def is_available(subject: str, name: str, default: bool = True) -> bool:
    async with get_session() as session:
        result = (await session.scalars(
            select(SubjectData.available)
            .where(SubjectData.subject == subject)
            .where(SubjectData.name == name)
        )).all()
        logger.debug(f"权限检查结果 ({subject=}, {name=}): {result}")
        return all(
            result or [default]
        )


def get_access_rule(plugin_name: str) -> Rule:
    async def check_access(
        subject_list: list[str] = Depends(get_subject_list)
    ) -> bool:
        results = [all([await is_available(
            subject,
            name,
        ) for subject in subject_list]) for name in [
            "all",
            f"plugin_{plugin_name}",
        ]]
        return all(results)
    return Rule(check_access)


@get_driver().on_startup
async def _() -> None:
    for matcher in matchers.provider[1]:
        if (not matcher.plugin_name) or matcher.type != "message":
            continue
        matcher.rule = matcher.rule & get_access_rule(matcher.plugin_name)
    logger.info(f"已对 {len(matchers.provider[1])} 个事件响应器添加权限检查规则！")
