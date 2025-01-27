from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args
from nonebot_plugin_larklang import LangHelper

alc = Alconna("wakatime", Subcommand("login"), Subcommand("rank"))
matcher = on_alconna(alc)
lang = LangHelper()
