from nonebot_plugin_alconna import Args, Subcommand, on_alconna, Alconna
from nonebot.matcher import Matcher
from nonebot_plugin_bag.commands.bag import STAR_COLORS
from .models import ControllableCharacter
from sqlalchemy import select
from .base.scheduler import Scheduler
from .utils.character import get_controllable_character
from .base.team import ControllableTeam
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import async_scoped_session


character = on_alconna(Alconna(
    "character",
    Args["index?", int],
    Subcommand(
        "weapon", 
        Subcommand("fix", Args["percent", int]),
        Subcommand("upgrade", Args["delta_level", int])
    ),
    Subcommand(
        "equipment",
        Args["equip_index?", int],
        Subcommand("put", Args["equipment_bag_index", int]),
        Subcommand("upgrade", Args["eq_delta_level", int]),
        Subcommand("remove")
    )
    # TODO 天赋
))
team = on_alconna(Alconna(
    "team",
    Args["character_index?", int],
    Subcommand("exchange", Args["chatacter_id?", int]),
    Subcommand("remove")
))


@character.assign("index")
async def _(index: int, session: async_scoped_session, matcher: Matcher, user_id: str = get_user_id()) -> None:
    scheduler = Scheduler()
    team = ControllableTeam(scheduler, matcher, user_id)
    character_data = (await session.scalars(
        select(ControllableCharacter).where(ControllableCharacter.user_id == user_id)
        .order_by(ControllableCharacter.experience.desc(), ControllableCharacter.character_id)
    )).all()[index]
    character = await get_controllable_character(character_data, team)
    template = {
        "c": {
            "name": await character.get_name(user_id),
            "star": character.star,
            "star_color": STAR_COLORS[character.star],
            ""
        }
    }

    
    

