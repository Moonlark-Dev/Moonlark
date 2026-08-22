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

import traceback

import httpx
from nonebot import get_bots, logger
from nonebot.adapters.qq.bot import Bot as QQBot

from .config import config
from .models import MenuPanelSettings, SyncResult

HELP_USER_ID = "mlsid::--lang=zh_hans"
MENU_ITEM_NAME_LIMIT = 10  # 菜单按钮名称上限，一个中文汉字算 2 个字符
PANEL_ITEM_DESC_LIMIT = 30  # 面板元素描述上限，一个中文汉字算 2 个字符


def text_width(text: str) -> int:
    """按 QQ 官方规则计算文本宽度：中文汉字算 2 个字符"""
    return sum(2 if ord(char) > 127 else 1 for char in text)


def build_menu_items(settings: MenuPanelSettings) -> list[dict]:
    """由配置生成 QQ 自定义菜单（C2C 单聊底部，最多 10 个顶层菜单项）"""
    items: list[dict] = [
        {"type": "send_message", "name": "帮助", "send_message": "/help"},
        {"type": "link", "name": "在线帮助", "link": config.menupanel_frontend_help_url},
    ]
    for command in settings.commands:
        if text_width(command) + 1 > MENU_ITEM_NAME_LIMIT:
            logger.warning(f"menupanel: 指令名过长，已跳过菜单项: {command}")
            continue
        items.append({"type": "send_message", "name": f"/{command}", "send_message": f"/{command}"})
    return items[:10]


async def build_panel_items(commands: list[str]) -> list[dict]:
    """由配置生成指令面板元素（每个面板最多 20 个）"""
    from nonebot_plugin_larkhelp.__main__ import get_help_dict

    items: list[dict] = []
    for command in commands[:20]:
        try:
            help_dict = await get_help_dict(command, HELP_USER_ID)
            desc = help_dict["description"]
        except Exception:
            desc = command
        while text_width(desc) > PANEL_ITEM_DESC_LIMIT and desc:
            desc = desc[:-1]
        items.append({"type": "command", "name": command[:7], "desc": desc})
    return items


class QQApiError(Exception):
    pass


async def qq_request(bot: QQBot, method: str, path: str, json_body: dict | None = None) -> dict:
    """调用 QQ 官方 API"""
    url = str(bot.adapter.get_api_base()).rstrip("/") + path
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, url, json=json_body, headers=await bot.get_authorization_header())
    if response.status_code >= 300:
        raise QQApiError(f"HTTP {response.status_code}: {response.text[:200]}")
    return response.json() if response.content else {}


async def find_panel_id(bot: QQBot, scope: str) -> str | None:
    """查找 Moonlark 创建的同场景指令面板"""
    cursor = ""
    for _ in range(5):  # 每页最大 50 条，翻页兜底
        params = f"?scope={scope}&limit=50" + (f"&cursor={cursor}" if cursor else "")
        data = await qq_request(bot, "GET", f"/v2/panels{params}")
        for record in data.get("records", []):
            if record.get("panel", {}).get("remark") == config.menupanel_panel_remark:
                return record.get("panel_id")
        if data.get("is_end", True):
            break
        cursor = data.get("next_cursor", "")
    return None


async def sync_panels(bot: QQBot, commands: list[str]) -> str:
    """同步 C2C 与群聊场景的全局指令面板，返回结果描述"""
    items = await build_panel_items(commands)
    messages = []
    for scope, scope_name in (("c2c", "单聊"), ("group", "群聊")):
        panel = {"items": items, "remark": config.menupanel_panel_remark}
        try:
            panel_id = await find_panel_id(bot, scope)
            if panel_id is None:
                await qq_request(
                    bot, "POST", "/v2/panels", {"scope": scope, "target_type": "all", "panel": panel}
                )
                messages.append(f"{scope_name}面板已创建")
            else:
                await qq_request(bot, "PUT", f"/v2/panels/{panel_id}", {"panel": panel})
                messages.append(f"{scope_name}面板已更新")
        except QQApiError as e:
            messages.append(f"{scope_name}面板同步失败: {e}")
    return "；".join(messages)


async def sync_bot(bot: QQBot, settings: MenuPanelSettings) -> SyncResult:
    """将菜单与面板配置同步到单个 QQ 官方 bot"""
    try:
        await qq_request(bot, "PUT", "/v2/menu", {"menu": {"items": build_menu_items(settings)}})
        message = "自定义菜单已更新"
        if settings.commands:
            message += "；" + await sync_panels(bot, settings.commands)
        return SyncResult(self_id=bot.self_id, success=True, message=message)
    except Exception as e:
        logger.warning(f"menupanel: 同步到 bot {bot.self_id} 失败\n{traceback.format_exc()}")
        return SyncResult(self_id=bot.self_id, success=False, message=str(e))


async def sync_all(settings: MenuPanelSettings) -> list[SyncResult]:
    """遍历所有在线的 QQ 官方 bot 执行同步"""
    results = []
    for bot in get_bots().values():
        if isinstance(bot, QQBot) and bot.ready:
            results.append(await sync_bot(bot, settings))
    return results
