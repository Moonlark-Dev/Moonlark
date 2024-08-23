#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from nonebot_plugin_alconna import on_alconna, Alconna, Args, Option, Subcommand
from typing import Optional
from ..nonebot_plugin_larkuser import patch_matcher
from ..nonebot_plugin_larklang import LangHelper

alc = Alconna(
    "ftt",
    Args["seed?", str],
    Subcommand("ranking"),
    Subcommand("points"),
    Subcommand("exchange", Args["count?", int]),
)
ftt = on_alconna(alc)
lang = LangHelper()

patch_matcher(ftt)
