"""决策建议辅助模块

基于当前状态和群聊总结，生成"决策建议"文本。
作为 LLM Prompt 中的提示，不是强制指令。

注意：本模块使用算法生成建议，不调用 LLM。
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain


class ActionAdvisor:
    """决策建议辅助模块（算法生成）"""

    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main

    def get_suggestions(self, state: dict, summary: str) -> str:
        """生成决策建议文本

        Args:
            state: 当前状态字典，包含：
                - sleep_mode: bool
                - blog_status: str
                - last_blog_time: Optional[datetime]
                - proactive_info: dict
                - current_activity: Optional[str]
                - mood: dict
            summary: 群聊总结文本

        Returns:
            建议文本
        """
        suggestions = []

        # 1. 睡眠建议
        sleep_suggestion = self._check_sleep_suggestion(state)
        if sleep_suggestion:
            suggestions.append(sleep_suggestion)

        # 2. 博客建议
        blog_suggestion = self._check_blog_suggestion(state)
        if blog_suggestion:
            suggestions.append(blog_suggestion)

        # 3. 私聊建议
        proactive_suggestion = self._check_proactive_suggestion(state)
        if proactive_suggestion:
            suggestions.append(proactive_suggestion)

        # 4. 自主活动建议
        self_action_suggestion = self._check_self_action_suggestion(state)
        if self_action_suggestion:
            suggestions.append(self_action_suggestion)

        # 5. 心情相关建议
        mood_suggestion = self._check_mood_suggestion(state)
        if mood_suggestion:
            suggestions.append(mood_suggestion)

        return "\n".join(suggestions) if suggestions else "无特别建议，请根据当前情况自主决策。"

    def _check_sleep_suggestion(self, state: dict) -> str:
        """检查睡眠相关建议"""
        if state.get("sleep_mode"):
            return "当前在睡眠中，只能选择 wake_up 或 stay_sleep。"

        # 检查群聊沉寂时间
        minutes_since_msg = self.moonlark_main.get_minutes_since_last_group_message()
        if minutes_since_msg > 40:
            return f"群聊已沉寂 {int(minutes_since_msg)} 分钟，可以考虑 go_to_sleep。"

        return ""

    def _check_blog_suggestion(self, state: dict) -> str:
        """检查博客相关建议"""
        blog_status = state.get("blog_status", "IDLE")

        if blog_status == "DRAFTING":
            draft = state.get("draft")
            if draft:
                word_count = draft.get("word_count", 0)
                continue_count = draft.get("continue_count", 0)
                return (
                    f"有未完成的草稿《{draft.get('topic', '未知')}》，"
                    f"当前 {word_count} 字/续写 {continue_count} 次，"
                    f"可以 continue_draft 或 abort_draft。"
                )
            return "有未完成的草稿，可以 continue_draft 或 abort_draft。"

        if blog_status == "IDLE":
            cooldown_remaining = state.get("cooldown_remaining", 0)
            if cooldown_remaining > 0:
                minutes = cooldown_remaining // 60
                return f"博客冷却中，还需等待 {minutes} 分钟。"
            else:
                return "可以考虑写一篇博客（blog_action: {\"start_new_topic\": \"主题\"}）。"

        return ""

    def _check_proactive_suggestion(self, state: dict) -> str:
        """检查私聊相关建议"""
        proactive_info = state.get("proactive_info", {})
        if not proactive_info:
            return ""

        suggestions = []
        for user_id, info in proactive_info.items():
            if not info.get("in_cooldown"):
                if info.get("replied"):
                    suggestions.append(f"用户 {user_id} 已回复上次私聊，可以再次私聊。")
                else:
                    last_chat = info.get("last_chat")
                    if last_chat:
                        minutes_ago = (datetime.now() - last_chat).total_seconds() // 60
                        suggestions.append(
                            f"用户 {user_id} 在 {int(minutes_ago)} 分钟前收到私聊但未回复。"
                        )

        return "\n".join(suggestions)

    def _check_self_action_suggestion(self, state: dict) -> str:
        """检查自主活动相关建议"""
        current_activity = state.get("current_activity")
        if current_activity:
            return ""  # 已有活动，不建议

        return "当前无自主活动，可以安排一个 self_action（如学习CSS、做拉伸、看番等）。"

    def _check_mood_suggestion(self, state: dict) -> str:
        """检查心情相关建议"""
        mood = state.get("mood", {})
        emotion = mood.get("emotion", "neutral")
        intensity = mood.get("intensity", 0.5)

        if emotion == "sad" and intensity > 0.7:
            return "当前心情较低落，可以考虑做一些轻松的事情。"
        if emotion == "bored" and intensity > 0.6:
            return "当前感到无聊，可以考虑找人聊天或做点有趣的事。"

        return ""
