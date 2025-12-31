#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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

from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna, MultiVar
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkutils import get_user_id, review_text

from ..lang import lang
from ..models import UserProfile


alc = Alconna(
    "chat",
    Subcommand("profile", Subcommand("set", Args["content", MultiVar(str)])),
)
profile_matcher = on_alconna(alc, priority=10)
patch_matcher(profile_matcher)


@profile_matcher.assign("profile.set")
async def handle_profile_set(
    session: async_scoped_session,
    content: tuple[str, ...],
    user_id: str = get_user_id(),
) -> None:
    profile_text = " ".join(content)

    if not profile_text.strip():
        await lang.finish("profile.empty_input", user_id)

    # 审核纯文本内容
    review_result = await review_text(profile_text)
    if not review_result["compliance"]:
        await lang.finish("profile.review_failed", user_id, review_result["message"])

    # 保存或更新 profile
    existing_profile = await session.get(UserProfile, {"user_id": user_id})
    if existing_profile:
        existing_profile.profile_content = profile_text
    else:
        session.add(UserProfile(user_id=user_id, profile_content=profile_text))

    await session.commit()
    await lang.finish("profile.set_success", user_id)


@profile_matcher.assign("profile")
async def handle_profile_view(
    session: async_scoped_session,
    user_id: str = get_user_id(),
) -> None:
    profile = await session.get(UserProfile, {"user_id": user_id})

    if profile and profile.profile_content:
        await lang.finish("profile.current", user_id, profile.profile_content)
    else:
        await lang.finish("profile.empty", user_id)
