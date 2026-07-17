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

import json

from nonebot import on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_chat.core.session import get_session_directly, group_disable, groups, reset_session
from nonebot_plugin_chat.core.session.base import BaseSession

from ..lang import lang
from ..models import ChatGroup, PrivateChatConfig
from ..utils.timing_stats import timing_stats_manager


class CommandHandler:
    def __init__(
        self,
        matcher: Matcher,
        bot: Bot,
        session: async_scoped_session,
        message: Message,
        group_id: str,
        user_id: str,
        is_private_chat: bool = False,
    ):
        self.matcher = matcher
        self.bot = bot
        self.session = session
        self.group_id = group_id
        self.user_id = user_id
        self.argv = message.extract_plain_text().split(" ")
        self.is_private_chat = is_private_chat
        self.group_config: ChatGroup | None = None
        self.private_config: PrivateChatConfig | None = None

    async def setup(self) -> "CommandHandler":
        if self.is_private_chat:
            self.private_config = (await self.session.get(PrivateChatConfig, {"user_id": self.user_id})) or PrivateChatConfig(
                user_id=self.user_id, enabled=False,
            )
        else:
            from nonebot_plugin_openai import is_ai_enabled_for_group

            if not await is_ai_enabled_for_group(self.bot, self.group_id):
                await lang.finish("command.not_available", self.user_id)
            self.group_config = (await self.session.get(ChatGroup, {"group_id": self.group_id})) or ChatGroup(
                group_id=self.group_id, enabled=False,
            )
        return self

    def is_group_enabled(self) -> bool:
        if self.is_private_chat:
            return self.private_config.enabled if self.private_config else False
        return self.group_config.enabled if self.group_config else False

    async def handle_switch(self) -> None:
        if self.is_group_enabled():
            await self.handle_off()
        else:
            await self.handle_on()

    async def merge_group_config(self) -> None:
        await self.session.merge(self.group_config)
        await self.session.commit()

    async def handle_off(self) -> None:
        if self.is_private_chat:
            self.private_config.enabled = False
            await self.session.merge(self.private_config)
            await self.session.commit()
            await lang.finish("command.switch_private.disabled", self.user_id)
        else:
            self.group_config.enabled = False
            await self.merge_group_config()
            await group_disable(self.group_id)
            await lang.finish("command.switch.disabled", self.user_id)

    async def handle_on(self) -> None:
        if self.is_private_chat:
            self.private_config.enabled = True
            await self.session.merge(self.private_config)
            await self.session.commit()
            await lang.finish("command.switch_private.enabled", self.user_id)
        else:
            self.group_config.enabled = True
            await self.merge_group_config()
            await lang.finish("command.switch.enabled", self.user_id)

    async def handle_desire(self) -> None:
        session = await self.get_group_session()
        details = await session.get_probability_details()
        await lang.send(
            "command.desire.get",
            self.user_id,
            round(details["final_probability"] * 100, 2),  # 消息触发概率 (%)
            details["accumulated_length"],  # 当前累计文本长度
            round(details["base_probability"] * 100, 2),  # 基础触发概率 (%)
            details["ghot_coefficient"],  # 群热度分数系数
            round(details["interest_coefficient"], 2),  # 兴趣系数
        )

    async def handle_mute(self) -> None:
        session = await self.get_group_session()
        await session.mute()
        await lang.finish("command.mute", self.user_id)

    async def handle_unmute(self) -> None:
        session = await self.get_group_session()
        session.mute_until = None
        await lang.finish("command.unmute", self.user_id)

    async def handle_calls(self) -> None:
        session = await self.get_group_session()
        await self.matcher.finish("\n".join(session.tool_calls_history))

    async def handle_reset(self) -> None:
        result = await reset_session(self.group_id)
        if result:
            await lang.finish("command.reset.success", self.user_id)
        else:
            await lang.finish("command.reset.not_found", self.user_id)

    async def handle_stop(self) -> None:
        session = await self.get_group_session()
        await session.processor.openai_messages.stop_fetcher()
        await lang.finish("command.stop", self.user_id)

    async def handle_stats(self) -> None:
        """处理统计命令"""
        # 获取当前会话的统计
        session_stats = timing_stats_manager.get_session_stats(self.group_id)
        # 获取全局统计
        global_stats = timing_stats_manager.get_global_stats()

        # 构建统计信息
        session_fetch = (
            f"{session_stats.avg_fetch_time_ms:.2f}ms" if session_stats and session_stats.avg_fetch_time_ms else "N/A"
        )
        session_fetch_count = session_stats.fetch_count if session_stats else 0
        session_reply = (
            f"{session_stats.avg_reply_time_ms:.2f}ms" if session_stats and session_stats.avg_reply_time_ms else "N/A"
        )
        session_reply_count = session_stats.reply_count if session_stats else 0

        global_fetch = f"{global_stats.avg_fetch_time_ms:.2f}ms" if global_stats.avg_fetch_time_ms else "N/A"
        global_fetch_count = global_stats.fetch_count
        global_reply = f"{global_stats.avg_reply_time_ms:.2f}ms" if global_stats.avg_reply_time_ms else "N/A"
        global_reply_count = global_stats.reply_count

        await lang.finish(
            "command.stats.result",
            self.user_id,
            session_fetch,
            session_fetch_count,
            session_reply,
            session_reply_count,
            global_fetch,
            global_fetch_count,
            global_reply,
            global_reply_count,
        )

    async def handle_block(self) -> None:
        if len(self.argv) < 2:
            await lang.finish("command.no_argv", self.user_id)

        target_type = self.argv[1]

        if target_type == "user":
            if len(self.argv) < 3:
                await lang.finish("command.no_argv", self.user_id)
            action = self.argv[2]
            blocked_list = json.loads(self.group_config.blocked_user)

            if action == "list":
                await lang.finish("command.block.user.list", self.user_id, ", ".join(blocked_list))

            if len(self.argv) < 4:
                await lang.finish("command.no_argv", self.user_id)
            target_id = self.argv[3]

            if action == "add":
                if target_id not in blocked_list:
                    blocked_list.append(target_id)
                    self.group_config.blocked_user = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.user.added", self.user_id, target_id)
                else:
                    await lang.finish("command.block.user.exists", self.user_id, target_id)
            elif action == "remove":
                if target_id in blocked_list:
                    blocked_list.remove(target_id)
                    self.group_config.blocked_user = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.user.removed", self.user_id, target_id)
                else:
                    await lang.finish("command.block.user.not_found", self.user_id, target_id)

        elif target_type == "keyword":
            if len(self.argv) < 3:
                await lang.finish("command.no_argv", self.user_id)
            action = self.argv[2]
            blocked_list = json.loads(self.group_config.blocked_keyword)

            if action == "list":
                await lang.finish("command.block.keyword.list", self.user_id, ", ".join(blocked_list))

            if len(self.argv) < 4:
                await lang.finish("command.no_argv", self.user_id)
            target_keyword = self.argv[3]

            if action == "add":
                if target_keyword not in blocked_list:
                    blocked_list.append(target_keyword)
                    self.group_config.blocked_keyword = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.keyword.added", self.user_id, target_keyword)
                else:
                    await lang.finish("command.block.keyword.exists", self.user_id, target_keyword)
            elif action == "remove":
                if target_keyword in blocked_list:
                    blocked_list.remove(target_keyword)
                    self.group_config.blocked_keyword = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.keyword.removed", self.user_id, target_keyword)
                else:
                    await lang.finish("command.block.keyword.not_found", self.user_id, target_keyword)
        else:
            await lang.finish("command.no_argv", self.user_id)

    async def handle_ignore_mention(self) -> None:
        if len(self.argv) < 3:
            await lang.finish("command.no_argv", self.user_id)

        action = self.argv[2]
        ignore_list = json.loads(self.group_config.ignore_mention_user)

        if action == "list":
            await lang.finish("command.ignore_mention.list", self.user_id, ", ".join(ignore_list))

        if len(self.argv) < 4:
            await lang.finish("command.no_argv", self.user_id)
        target_id = self.argv[3]

        if action == "add":
            if target_id not in ignore_list:
                ignore_list.append(target_id)
                self.group_config.ignore_mention_user = json.dumps(ignore_list)
                await self.merge_group_config()
                await lang.finish("command.ignore_mention.added", self.user_id, target_id)
            else:
                await lang.finish("command.ignore_mention.exists", self.user_id, target_id)
        elif action == "remove":
            if target_id in ignore_list:
                ignore_list.remove(target_id)
                self.group_config.ignore_mention_user = json.dumps(ignore_list)
                await self.merge_group_config()
                await lang.finish("command.ignore_mention.removed", self.user_id, target_id)
            else:
                await lang.finish("command.ignore_mention.not_found", self.user_id, target_id)

    async def handle_dropping(self) -> None:
        """处理礼物掉落开关命令"""
        if len(self.argv) < 2:
            await lang.finish("command.no_argv", self.user_id)
        action = self.argv[1]
        if action == "on":
            self.group_config.dropping_enabled = True
            await self.merge_group_config()
            await lang.finish("command.dropping.enabled", self.user_id)
        elif action == "off":
            self.group_config.dropping_enabled = False
            await self.merge_group_config()
            await lang.finish("command.dropping.disabled", self.user_id)
        else:
            await lang.finish("command.no_argv", self.user_id)

    async def handle_compact(self) -> None:
        """处理 compact 命令：分析待定笔记并重置消息队列"""
        from nonebot_plugin_larkutils.config import config as lark_config

        # 验证 superuser
        if self.user_id not in lark_config.superusers:
            await lang.finish("command.compact.no_permission", self.user_id)

        # 解析可选的会话 ID
        target_session_id = self.argv[1] if len(self.argv) > 1 else self.group_id

        # 获取目标会话
        if target_session_id not in groups:
            await lang.finish("command.compact.not_found", self.user_id, target_session_id)

        session = groups[target_session_id]

        # 如果有缓存消息，先分析待定笔记
        if session.cached_messages:
            await session.processor._analyze_pending_notes()
            await lang.send("command.compact.pending_notes_analyzed", self.user_id)

        # 重置消息队列
        await session.processor.openai_messages._reset_and_clear_db(target_session_id)

        # 重新注入待定笔记
        await session.processor._inject_pending_notes_to_openai_messages()

        await lang.finish("command.compact.success", self.user_id, target_session_id)

    async def handle(self) -> None:
        if not self.argv or not self.argv[0]:
            await lang.finish("command.no_argv", self.user_id)

        if self.is_private_chat and self.argv[0] not in ("switch", "on", "off"):
            await lang.finish("command.private_only_switch", self.user_id)

        match self.argv[0]:
            case "switch":
                await self.handle_switch()
            case "desire":
                await self.handle_desire()
            case "mute":
                await self.handle_mute()
            case "unmute":
                await self.handle_unmute()
            case "calls":
                await self.handle_calls()
            case "on":
                await self.handle_on()
            case "off":
                await self.handle_off()
            case "block":
                await self.handle_block()
            case "ignore-mention":
                await self.handle_ignore_mention()
            case "reset":
                await self.handle_reset()
            case "stop":
                await self.handle_stop()
            case "stats":
                await self.handle_stats()
            case "dropping":
                await self.handle_dropping()
            case "compact":
                await self.handle_compact()
            case _:
                await lang.finish("command.no_argv", self.user_id)

    async def get_group_session(self) -> BaseSession:
        try:
            return get_session_directly(self.group_id)
        except KeyError:
            if self.is_group_enabled():
                await lang.finish("command.not_inited", self.user_id)
            else:
                await lang.finish("command.disabled", self.user_id)


@on_command("chat").handle()
async def _(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    session: async_scoped_session,
    message: Message = CommandArg(),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    is_private_chat = event.get_session_id() == event.get_user_id()
    handler = CommandHandler(matcher, bot, session, message, group_id, user_id, is_private_chat)
    await handler.setup()
    await handler.handle()
