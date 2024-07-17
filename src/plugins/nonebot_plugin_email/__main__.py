from typing import Literal
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from src.plugins.nonebot_plugin_larkuser.utils.matcher import patch_matcher

alc = Alconna(
    "email",
    Subcommand("claim", Args["email_id", int | Literal["all"], "all"]),
    Subcommand("unread", Args["email_id", int | Literal["all"], "all"]),
)
email = on_alconna(alc)
patch_matcher(email)
