from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot_plugin_openai.types import Message as OpenAIMessage
from nonebot.log import logger
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_openai import generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select

import asyncio
import json
import random
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, AsyncGenerator, Literal

from .message import MessageQueue
from ..models import ChatGroup, Sticker, UserProfile
from ..types import CachedMessage

from ..utils.message import generate_message_string
from ..utils import parse_message_to_string
from ..utils.ai_agent import AskAISession
from ..utils.emoji import QQ_EMOJI_MAP
from ..utils.image import query_image_content
from ..utils.note_manager import get_context_notes
from ..utils.sticker_manager import get_sticker_manager
from ..utils.tool_manager import ToolManager
from ..utils.tools.sticker import StickerTools
from ..utils.status_manager import get_status_manager

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.session.base import BaseSession


class MessageProcessor:

    def __init__(self, session: "BaseSession"):
        self.openai_messages = MessageQueue(self, 50)
        self.session = session
        self.enabled = True
        self.tool_manager = ToolManager(self)
        self.ai_agent = AskAISession(self.session.lang_str, self.tool_manager)
        self.sticker_manager = get_sticker_manager()
        self.cold_until = datetime.now()
        self.blocked = False
        self._latest_reasioning_content_cache = ""
        self.sticker_tools = StickerTools(self.session)
        self.functions = []

    async def query_image(self, image_id: str, query_prompt: str) -> str:
        return await query_image_content(image_id, query_prompt, self.session.lang_str)

    async def setup(self) -> None:
        self.functions = await self.tool_manager.select_tools("group")
        await self.ai_agent.setup()
        asyncio.create_task(self.loop())

    async def send_reaction(self, message_id: str, emoji_id: str) -> str:
        if isinstance(self.session.bot, OB11Bot) and self.session.is_napcat_bot():
            await self.session.bot.call_api("set_msg_emoji_like", message_id=message_id, emoji_id=emoji_id)
            return await self.session.text("message.reaction_success", QQ_EMOJI_MAP.get(emoji_id))
        else:
            return await self.session.text("message.reaction_failed")

    async def refuse_interaction_request(self, id_: str, type_: Literal["dodge", "bite"]) -> str:
        """
        拒绝交互请求

        Args:
            id_: 交互请求 ID
            type_: 拒绝类型，dodge（躲开）或 bite（躲开并咬一口）

        Returns:
            处理结果消息
        """
        interaction = self.session.remove_pending_interaction(id_)
        if interaction is None:
            return await self.session.text("interaction.not_found")

        action_name = interaction["action"]["name"]
        nickname = interaction["nickname"]

        # 根据拒绝类型生成不同的提示
        if type_ == "dodge":
            # 发送拒绝消息到会话
            refuse_msg = await self.session.text(f"rua.actions.{action_name}.refuse_msg")
            await self.send_message(refuse_msg)
            return await self.session.text(f"rua.actions.{action_name}.refuse_prompt", nickname)
        else:  # bite
            # 躲开并咬一口
            refuse_msg = await self.session.text("rua.bite_msg", nickname)
            await self.send_message(refuse_msg)
            return await self.session.text("rua.bite_prompt", nickname)

    async def judge_user_behavior(self, nickname: str, score: int, reason: str) -> str:
        # 获取用户 ID
        users = await self.session.get_users()
        if not (user_id := users.get(nickname)):
            return await self.session.text("judge.user_not_found", nickname)
        user = await get_user(user_id)
        if user.get_register_time() is None:
            return await self.session.text("judge.user_not_registered", nickname)
        # 限制分数范围
        score = max(-2, min(2, score))
        # 检查冷却时间和每日上限
        dt = datetime.now()
        user_cache = user.get_config_key("chat_fav_judge_cache", [0, 0])
        last_judge_time, daily_score = user_cache
        if dt - datetime.fromtimestamp(last_judge_time) < timedelta(hours=1):
            return await self.session.text("judge.cooldown", nickname)
        if datetime.fromtimestamp(last_judge_time).date() != datetime.now().date():
            daily_score = 0
        delta = score * 0.0002
        if abs(daily_score + delta) > 0.005:
            return await self.session.text("judge.daily_limit", nickname)
        await user.set_config_key("chat_fav_judge_cache", [dt.timestamp(), daily_score + delta])
        await user.add_fav(delta)
        logger.info(f"AI judged user {user_id} ({nickname}): {score} ({reason}), delta={delta}")
        return await self.session.text("judge.success", nickname, reason)

    async def loop(self) -> None:
        # 在开始循环前等待消息队列从数据库恢复完成
        await self.openai_messages.wait_for_restore()
        while self.enabled:
            try:
                await self.get_message()
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(5)

    async def poke(self, target_name: str) -> str:
        target_id = (await self.session.get_users()).get(target_name)
        if target_id:
            await self.session.send_poke(target_id)
            return await self.session.text("poke.success", target_name)
        else:
            return await self.session.text("poke.not_found")

    async def get_message(self) -> None:
        if not self.session.message_queue:
            await asyncio.sleep(3)
            return
        trigger_mode: Literal["none", "probability", "all"] = "none"

        item = self.session.message_queue.pop(0)

        if item[0] == "event":
            # 处理事件类型队列项
            event_prompt, trigger_mode = item[1]  # type: ignore
            content = await self.session.text(
                "prompt.event_template", datetime.now().strftime("%H:%M:%S"), event_prompt
            )
            self.openai_messages.append_user_message(content)

        elif item[0] == "message":
            # 处理消息类型队列项
            message, event, state, user_id, nickname, dt, mentioned, message_id = item[1]
            text = await parse_message_to_string(message, event, self.session.bot, state, self.session.lang_str)
            if not text:
                return
            if "@Moonlark" not in text and mentioned:
                text = f"@Moonlark {text}"
            msg_dict: CachedMessage = {
                "content": text,
                "nickname": nickname,
                "send_time": dt,
                "user_id": user_id,
                "self": False,
                "message_id": message_id,
            }
            await self.process_messages(msg_dict)
            self.session.cached_messages.append(msg_dict)
            await self.session.on_cache_posted()
            trigger_mode = "probability" if not mentioned else "all"
        if (
            trigger_mode == "all" or trigger_mode == "probability" and not self.session.message_queue
        ) and not self.blocked:
            asyncio.create_task(self.generate_reply(trigger_mode == "all"))

    async def handle_timer(self, description: str) -> None:
        await self.session.add_event(
            await self.session.text("prompt.timer_triggered", datetime.now().strftime("%H:%M:%S"), description), "all"
        )

    async def leave_for_a_while(self) -> None:
        await self.session.mute()

    async def generate_reply(self, important: bool = False) -> None:
        # 如果在冷却期或消息为空，直接返回
        if self.cold_until > datetime.now():
            return
        if len(self.openai_messages.messages) <= 0 or not self.openai_messages.is_last_message_from_user():
            return
        self.cold_until = datetime.now() + timedelta(seconds=5)

        # 检查是否应该触发回复
        if not important:
            probability = await self.session.get_probability()
            logger.debug(
                f"Accumulated length: {self.session.accumulated_text_length}, Trigger probability: {probability:.2%}"
            )
            if random.random() > probability:
                return

        logger.info(f"Generating reply ({important=})...")
        await self.openai_messages.fetch_reply()

    async def append_tool_call_history(self, call_string: str) -> None:
        self.session.tool_calls_history.append(
            await self.session.text("tools.template", datetime.now().strftime("%H:%M"), call_string)
        )
        self.session.tool_calls_history = self.session.tool_calls_history[-5:]

    async def send_function_call_feedback(
        self, call_id: str, name: str, param: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        match name:
            case "browse_webpage":
                text = await self.session.text("tools.browse", param.get("url"))
            case "request_wolfram_alpha":
                text = await self.session.text("tools.wolfram", param.get("question"))
            case "web_search":
                text = await self.session.text("tools.search", param.get("keyword"))
            case _:
                return call_id, name, param
        await self.append_tool_call_history(text)
        return call_id, name, param

    async def send_message(self, message_content: str, reply_message_id: str | None = None) -> None:
        # 增加连续发送消息计数
        self.session.last_activate = datetime.now()
        message = await self.session.format_message(message_content)
        if reply_message_id:
            message = message.reply(reply_message_id)
        await message.send(target=self.session.target, bot=self.session.bot)
        self.session.accumulated_text_length = 0

    def append_user_message(self, msg_str: str) -> None:
        self.openai_messages.append_user_message(msg_str)

    async def process_messages(self, msg_dict: CachedMessage) -> None:
        async with get_session() as session:
            r = await session.get(ChatGroup, {"group_id": self.session.session_id})

            # Check for blocked user
            blocked_user = r and msg_dict["user_id"] in json.loads(r.blocked_user)

            # Check for blocked keywords
            blocked_keyword = False
            if r:
                keywords = json.loads(r.blocked_keyword)
                content = msg_dict.get("content", "")
                if isinstance(content, str):
                    for keyword in keywords:
                        if keyword in content:
                            blocked_keyword = True
                            break

            self.blocked = blocked_user or blocked_keyword

            if not self.blocked:
                msg_str = generate_message_string(msg_dict)
                self.append_user_message(msg_str)
            if not self.blocked and not msg_dict["self"]:
                content = msg_dict.get("content", "")
                if isinstance(content, str) and content:
                    cleaned = re.sub(r"\[.*?\]", "", content)
                    cleaned = re.sub(r"\s+", " ", cleaned).strip()
                    self.session.accumulated_text_length += len(cleaned)
                logger.debug(f"Accumulated text length: {self.session.accumulated_text_length}")

    def get_message_content_list(self) -> list[str]:
        l = []
        for msg in self.openai_messages.messages:
            if isinstance(msg, dict):
                if "content" in msg and msg["role"] == "user":
                    l.append(str(msg["content"]))
            elif hasattr(msg, "content"):
                l.append(str(msg.content))
        return l

    async def _get_user_profiles(self) -> list[str]:
        """根据昵称获取用户的 profile 信息"""
        profiles = []
        async with get_session() as session:
            for nickname, user_id in (await self.session._get_users_in_cached_message()).items():
                if not (profile := await session.get(UserProfile, {"user_id": user_id})):
                    profile = await self.session.text("prompt_group.user_profile_not_found")
                    is_profile_found = False
                else:
                    profile = profile.profile_content
                    is_profile_found = True
                if isinstance(self.session.bot, OB11Bot):
                    try:
                        member_info = await self.session.get_user_info(user_id)
                    except Exception as e:
                        member_info = None
                else:
                    member_info = None
                user = await get_user(user_id)
                fav = user.get_fav()
                fav_level = await user.get_fav_level()
                if member_info:
                    profiles.append(
                        await self.session.text(
                            "prompt_group.group_member_info",
                            nickname,
                            member_info["role"],
                            member_info["sex"],
                            fav,
                            fav_level,
                            datetime.fromtimestamp(member_info["join_time"]).strftime("%Y-%m-%d"),
                            profile,
                        )
                    )
                elif fav > 0 or is_profile_found:
                    profiles.append(
                        await self.session.text("prompt_group.member_info", nickname, fav, fav_level, profile)
                    )
        return profiles

    async def generate_sticker_recommendations(self) -> AsyncGenerator[str, None]:
        chat_history = "\n".join(self.get_message_content_list())
        emotion_type = get_status_manager().get_status()[0].value
        async with get_session() as session:
            results = await session.scalars(
                select(Sticker).where(
                    Sticker.context_keywords.isnot(None), Sticker.emotion.isnot(None), Sticker.labels.isnot(None)
                )
            )
            for sticker in results:
                if sticker.emotion == emotion_type:
                    yield f"- {sticker.id}: {sticker.description}"
                    break
                for keyword in json.loads(sticker.context_keywords or "[]"):
                    if keyword in chat_history:
                        yield f"- {sticker.id}: {sticker.description}"
                        break
                for label in json.loads(sticker.labels or "[]"):
                    if label in chat_history or label == emotion_type:
                        yield f"- {sticker.id}: {sticker.description}"
                        break

    async def generate_system_prompt(self) -> OpenAIMessage:
        chat_history = "\n".join(self.get_message_content_list())
        # 获取相关笔记
        note_manager = await get_context_notes(self.session.session_id)
        notes, notes_from_other_group = await note_manager.filter_note(chat_history)

        # 获取用户 profile 信息
        user_profiles = await self._get_user_profiles()

        # 格式化 profile 信息
        if user_profiles:
            profiles_text = "\n".join(user_profiles)
        else:
            profiles_text = await self.session.text("prompt.profile.none")

        async def format_note(note):
            created_time = datetime.fromtimestamp(note.created_time).strftime("%y-%m-%d")
            return await self.session.text("prompt.note.format", note.content, note.id, created_time)

        status_manager = get_status_manager()
        mood, mood_reason, activity, remain_minutes = status_manager.get_status()

        mood_text = await self.session.text(f"status.mood.{mood.value}")

        # status_prompt = await self.session.text("status.info", , activity, remain_minutes)

        return generate_message(
            await self.session.text(
                "prompt_group.default",
                (
                    "\n".join([await format_note(note) for note in notes])
                    if notes
                    else await self.session.text("prompt.note.none")
                ),
                datetime.now().isoformat(),
                self.session.session_name,
                (
                    "\n".join([await format_note(note) for note in notes_from_other_group])
                    if notes_from_other_group
                    else await self.session.text("prompt.note.none")
                ),
                profiles_text,
                mood_text,
                status_manager.get_mood_retention(),
                mood_reason,
                activity,
                remain_minutes,
            ),
            "system",
        )

    async def handle_recall(self, message_id: str, message_content: str) -> None:
        await self.session.add_event(
            await self.session.text(
                "prompt.recall",
                datetime.now().strftime("%H:%M:%S"),
                message_id,
                message_content,
            ),
            "probability",
        )

    async def handle_poke(self, operator_name: str, target_name: str, to_me: bool) -> None:
        if to_me:
            await self.session.add_event(
                await self.session.text("prompt.poke.to_me", datetime.now().strftime("%H:%M:%S"), operator_name), "all"
            )
            # 注意：由于现在事件是异步处理的，blocked 标志不再需要在 poke 中设置
            # 事件会在 get_message 中被处理并直接生成回复
        else:
            await self.session.add_event(
                await self.session.text(
                    "prompt.poke.to_other",
                    datetime.now().strftime("%H:%M:%S"),
                    operator_name,
                    target_name,
                ),
                "probability",
            )

    async def handle_reaction(self, message_string: str, operator_name: str, emoji_id: str) -> None:
        await self.session.add_event(
            await self.session.text(
                "prompt.reaction",
                datetime.now().strftime("%H:%M:%S"),
                operator_name,
                message_string,
                QQ_EMOJI_MAP[emoji_id],
            ),
            "probability",
        )
