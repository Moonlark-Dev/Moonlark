from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from sqlalchemy import Lateral
from ..nonebot_plugin_larkuser.matcher import patch_matcher

alc = Alconna(
    "email",
    Subcommand("view", Args["email_id", int]),
    Subcommand("claim", Args["email_id", int | Lateral["all"], "all"]),
    Subcommand("read", Args["email_id", int | Lateral["all"], "all"]),
)
email = on_alconna(alc)
patch_matcher(email)
