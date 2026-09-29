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

"""基于 Jev（TypeSafe System One）的判定

模型（Chat 应用）的输出不再要求是 JSON：它只输出自然语言的思考文本，
mood / 兴趣 / 好感度 / 是否需要回复改由 Jev 依据

- 聊天上下文（``chat_context``）
- 模型的 ``reasoning_content``
- 模型本轮的输出（``model_output``）
- 实际通过 ``send_message`` 发送的消息（``sent_messages``）

来判定。问题文本全部放在 ``src/lang/<lang>/jev.yaml``，经 LarkLang 本地化。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from nonebot.log import logger

from nonebot_plugin_jev import (
    ChoiceAnswer,
    JevNotConfigured,
    NoulAnswer,
    Question,
    ScoreAnswer,
    ask,
    choice,
    lang_ref,
    noul,
    score,
)
from nonebot_plugin_jev import lang as jev_lang

from ..models import PreTriggerSignals
from ..types import EMOTIONS

if TYPE_CHECKING:
    from ..core.processor import MessageProcessor

# 回复后判定的常量
MOOD_INTENSITY_LEVELS = 4  # 心情强度问题的等级数
INTEREST_LEVELS = 4  # 兴趣问题的等级数
MOOD_INTENSITY_RANGE = (0.5, 1.2)  # 与旧版 ModelResponse.mood_intensity 的取值范围一致
REPLY_REQUIRED_THRESHOLD = 0.7  # reply_required Noul 达到该值才提示模型补发消息
NUL_THRESHOLD = 0.5  # 触发预处理的 Noul 判定阈值

# 好感度评价的选项（与 src/lang/zh_hans/jev.yaml 中 reply.favor_score.criteria 的键一致）
FAVOR_SCORE_KEYS = ("2", "1", "0", "-1", "-2")

# 未配置 API Key 时每轮回复都会走到这里，只提示一次避免刷屏
_not_configured_warned = False


def _log_jev_failure(identify: str, session_id: str, error: Exception) -> None:
    global _not_configured_warned
    where = f"[JevJudge:{session_id}]" if session_id else "[JevJudge]"
    if isinstance(error, JevNotConfigured):
        if not _not_configured_warned:
            _not_configured_warned = True
            logger.warning(f"{where} {identify} 跳过：{error}（此后不再重复提示）")
        else:
            logger.debug(f"{where} {identify} 跳过：{error}")
    else:
        logger.warning(f"{where} {identify} 失败: {error}")


def _extract_reasoning(message: Any) -> str:
    """从一条对话消息里读取模型的思考内容（兼容 dict 与对象、reasoning_content 与 reasoning）"""
    if isinstance(message, dict):
        for key in ("reasoning_content", "reasoning"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""
    for attr in ("reasoning_content", "reasoning"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


@dataclass
class ReplyEvaluation:
    """一轮回复的 Jev 判定结果"""

    mood: Optional[str] = None  # MoodEnum 的值；None 表示无需变动
    mood_intensity: float = 0.8
    mood_reason: str = ""
    interest: Optional[float] = None  # 0-1；None 表示未取得
    favor_target: Optional[str] = None  # 被评价的昵称；None 表示无需评价
    favor_score: int = 0  # -2 ~ 2（0 表示不变动）
    favor_reason: str = ""
    reply_required: bool = False

    @property
    def favor_changed(self) -> bool:
        return bool(self.favor_target) and self.favor_score != 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _score_level(answer: ScoreAnswer, levels: int) -> int:
    """把连续的 score 收敛到 [0, levels-1] 的等级下标"""
    return int(_clamp(round(answer.score), 0, levels - 1))


async def evaluate_reply(
    processor: "MessageProcessor",
    reply_messages: list,
    outputs: list[str],
    round_start: datetime,
) -> Optional[ReplyEvaluation]:
    """在一轮回复结束后，用 Jev 判定 mood / 兴趣 / 好感度 / 是否漏发消息

    Args:
        processor: 当前会话的处理器
        reply_messages: 本轮新增的对话消息（用于读取 reasoning_content）
        outputs: 本轮模型输出的文本（非 JSON 的自然语言思考）
        round_start: 本轮回复开始的时间，用于筛选本轮实际发送出去的消息

    Returns:
        判定结果；Jev 不可用或未取得任何答案时返回 None（调用方按「跳过判定」处理）
    """
    session = processor.session
    lang_str = session.lang_str

    chat_context = await session.get_cached_messages_string(length=50, include_self_message=True)

    reasoning_content = "\n".join(rc for rc in (_extract_reasoning(message) for message in reply_messages) if rc)
    if reasoning_content:
        # 供 chat-monitor 的 thought 接口读取
        processor._latest_reasioning_content_cache = reasoning_content

    sent_messages = [
        str(message.get("content", ""))
        for message in session.cached_messages
        if message.get("self")
        and message.get("message_id")
        and (message.get("send_time") or round_start) >= round_start
    ]

    participants: list[str] = []
    for message in session.cached_messages:
        if message.get("self"):
            continue
        nickname = message.get("nickname") or ""
        if nickname and nickname not in participants:
            participants.append(nickname)

    from .status_manager import get_status_manager

    current_mood = get_status_manager().get_status()[0].value

    state = {
        "chat_context": chat_context,
        "reasoning_content": reasoning_content,
        "model_output": "\n".join(outputs),
        "sent_messages": sent_messages,
        "current_mood": current_mood,
        "participants": participants,
    }

    mood_criteria = {value: lang_ref(f"reply.mood.criteria.{value}") for value in [*EMOTIONS, "none"]}
    questions: dict[str, Question] = {
        "mood": choice(lang_ref("reply.mood.instructions"), criteria=mood_criteria),
        "mood_intensity": score(
            lang_ref("reply.mood_intensity.instructions"),
            criteria=[lang_ref(f"reply.mood_intensity.criteria.{i}") for i in range(MOOD_INTENSITY_LEVELS)],
        ),
        "interest": score(
            lang_ref("reply.interest.instructions"),
            criteria=[lang_ref(f"reply.interest.criteria.{i}") for i in range(INTEREST_LEVELS)],
        ),
        "reply_required": noul(lang_ref("reply.reply_required")),
    }
    if participants:
        questions["favor_target"] = choice(
            lang_ref("reply.favor_target.instructions"),
            criteria={**{name: name for name in participants}, "none": lang_ref("reply.favor_target.none")},
        )
        questions["favor_score"] = choice(
            lang_ref("reply.favor_score.instructions"),
            criteria={key: lang_ref(f"reply.favor_score.criteria.{key}") for key in FAVOR_SCORE_KEYS},
        )

    try:
        answers = await ask(state, questions, lang_str=lang_str, identify="Chat Reply Judge")
    except Exception as e:
        _log_jev_failure("回复判定", session.session_id, e)
        return None
    if not answers:
        logger.warning(f"[JevJudge:{session.session_id}] 回复判定没有取得任何答案")
        return None

    evaluation = ReplyEvaluation()

    mood_answer = answers.get("mood")
    if isinstance(mood_answer, ChoiceAnswer) and mood_answer.choice in EMOTIONS:
        evaluation.mood = mood_answer.choice
        mood_label = await jev_lang.text(f"reply.mood.criteria.{mood_answer.choice}", lang_str)
        evaluation.mood_reason = await jev_lang.text(
            "reply.mood_reason", lang_str, mood_label, f"{mood_answer.confidence:.0%}"
        )
        intensity_answer = answers.get("mood_intensity")
        if isinstance(intensity_answer, ScoreAnswer):
            low, high = MOOD_INTENSITY_RANGE
            evaluation.mood_intensity = low + (
                _score_level(intensity_answer, MOOD_INTENSITY_LEVELS) / (MOOD_INTENSITY_LEVELS - 1)
            ) * (high - low)

    interest_answer = answers.get("interest")
    if isinstance(interest_answer, ScoreAnswer):
        evaluation.interest = _score_level(interest_answer, INTEREST_LEVELS) / (INTEREST_LEVELS - 1)

    reply_answer = answers.get("reply_required")
    if isinstance(reply_answer, NoulAnswer):
        evaluation.reply_required = reply_answer.noul >= REPLY_REQUIRED_THRESHOLD

    target_answer = answers.get("favor_target")
    score_answer = answers.get("favor_score")
    if (
        isinstance(target_answer, ChoiceAnswer)
        and target_answer.choice in participants
        and isinstance(score_answer, ChoiceAnswer)
    ):
        try:
            score_value = int(score_answer.choice)
        except ValueError:
            score_value = 0
        if score_value != 0:
            evaluation.favor_target = target_answer.choice
            evaluation.favor_score = score_value
            score_label = await jev_lang.text(f"reply.favor_score.criteria.{score_answer.choice}", lang_str)
            evaluation.favor_reason = await jev_lang.text(
                "reply.favor_reason", lang_str, score_label, f"{score_answer.confidence:.0%}"
            )

    logger.debug(f"[JevJudge:{session.session_id}] {evaluation}")
    return evaluation


async def apply_reply_evaluation(processor: "MessageProcessor", evaluation: ReplyEvaluation) -> None:
    """把判定结果落到状态上：心情、兴趣、好感度（变动成功时向会话推送事件）"""
    session = processor.session

    if evaluation.mood:
        await processor.tool_manager.set_mood(evaluation.mood, evaluation.mood_reason, evaluation.mood_intensity)
        logger.debug(f"[JevJudge:{session.session_id}] 心情变动: {evaluation.mood} ({evaluation.mood_intensity:.2f})")

    if evaluation.interest is not None:
        session.set_interest(evaluation.interest)
        logger.debug(f"[JevJudge:{session.session_id}] Cached interest: {evaluation.interest:.2f}")

    if evaluation.favor_changed:
        result_text, changed = await processor.judge_user_behavior(
            evaluation.favor_target,  # type: ignore[arg-type]
            evaluation.favor_score,
            evaluation.favor_reason,
        )
        if changed:
            # 好感度变动成功：向会话推送一条事件，让上下文知道这次变动
            await session.add_event(result_text, "none")
            logger.info(
                f"[JevJudge:{session.session_id}] 好感度变动事件已推送: "
                f"{evaluation.favor_target} {evaluation.favor_score:+d}"
            )


PRE_TRIGGER_FIELDS = ("truncate", "help_needed", "emotional_support_needed", "chatting_alone", "tech_topic")


async def analyze_pre_trigger(chat_history: str, lang_str: str) -> Optional[PreTriggerSignals]:
    """触发概率的预处理：用 Jev 的 Noul 问题从最近的聊天记录中读出五个布尔信号

    Args:
        chat_history: 最近的聊天记录
        lang_str: 会话语言

    Returns:
        信号集合；Jev 不可用或没有取得任何答案时返回 None（此时跳过门控，按原概率处理）
    """
    questions = {field: noul(lang_ref(f"pre_trigger.{field}")) for field in PRE_TRIGGER_FIELDS}
    try:
        answers = await ask(chat_history, questions, lang_str=lang_str, identify="Pre-Trigger Analysis")
    except Exception as e:
        _log_jev_failure("触发预处理", "", e)
        return None
    if not answers:
        return None

    values = {}
    for field in PRE_TRIGGER_FIELDS:
        answer = answers.get(field)
        values[field] = isinstance(answer, NoulAnswer) and answer.noul >= NUL_THRESHOLD

    signals = PreTriggerSignals(**values)
    logger.debug(f"Pre-trigger signals: {signals}")
    return signals
