from nonebot import on_message, on_type
from nonebot.rule import to_me
from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkuser import get_user
from ..nonebot_plugin_larkutils import get_user_id
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.adapters import Message, Event

lang = LangHelper()

@on_type(PokeNotifyEvent, block=False).handle()
async def _(user_id: str = get_user_id()) -> None:
    if not event.get_plaintext():
        user = await get_user(user_id)
        if not user.is_registered():
            await lang.finish("poke.default", user_id)
        elif user.get_fav() <= 0.007:
            await lang.send("poke.normal", user_id)
        elif user.get_fav() <= 0.01:
            await lang.send("poke.like", user_id)
        await user.set_config_key("poke_count", user.get_config_key("poke_count", 0) + 1)

@on_message(rule=to_me(), block=False).handle()
async def _(event: Event, user_id: str = get_user_id()) -> None:
    if not event.get_plaintext():
        user = await get_user(user_id)
        if not user.is_registered():
            await lang.finish("at.default", user_id)
        elif user.get_fav() <= 0.007:
            await lang.send("at.normal", user_id)
        elif user.get_fav() <= 0.01:
            await lang.send("at.like", user_id)
        await user.set_config_key("at_count", user.get_config_key("at_count", 0) + 1)



