from nonebot import on_command, require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-wish",
    description="许愿",
    usage="/wish 内容",
    config=None,
)

require("nonebot_plugin_larkutils")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_larklang")

from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user, patch_matcher
from nonebot.adapters import Message
from nonebot.params import CommandArg

lang = LangHelper()

@patch_matcher(on_command("wish")).handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    text = message.extract_plain_text()
    user = await get_user(user_id)
    if await user.get_config_key("desire_25"):
        await lang.finish("repeat", user_id)
    elif not text:
        await lang.finish("empty", user_id)
    await user.set_config_key("desire_25", text)
    await user.add_fav(0.0015)
    await lang.finish("done", user_id)


