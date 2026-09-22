#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from nonebot_plugin_htmlrender import get_new_page
from nonebot_plugin_larkutils.url_validator import block_internal_request

from .exceptions import AccessDenied

if TYPE_CHECKING:
    from playwright.async_api import Request, Route


async def screenshot(url: str, wait: int = 1, **kwargs) -> bytes:
    blocked_urls: set[str] = set()

    async with get_new_page(**kwargs) as page:

        async def _route_handler(route: Route, request: Request) -> None:
            if request.is_navigation_request() and await block_internal_request(route, request):
                blocked_urls.add(request.url)

        await page.route("**/*", _route_handler)
        try:
            await page.goto(url)
        except Exception:
            if blocked_urls:
                raise AccessDenied from None
            raise
        await asyncio.sleep(wait)
        return await page.screenshot(type="jpeg", full_page=True)
