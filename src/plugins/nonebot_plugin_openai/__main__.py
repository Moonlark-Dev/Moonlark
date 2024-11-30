from nonebot_plugin_alconna import Alconna, on_alconna, Args, Option, Match
from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id
from ..nonebot_plugin_larkuser import patch_matcher

lang = LangHelper()
matcher = on_alconna(Alconna("cg", Args["prompt?"]), Option("-r|--reset"))
patch_matcher(matcher)


@matcher.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    """获取用户可用信息"""
    pass

@matcher.assign("prompt")
async def _(prompt: str, reset: Match[bool], user_id: str = get_user_id()) -> None:
    pass

