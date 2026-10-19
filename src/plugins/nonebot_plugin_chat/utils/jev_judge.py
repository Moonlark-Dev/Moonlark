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
from typing import TYPE_CHECKING, Any, Literal, Optional, Sequence

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
SLIDING_WINDOW_RELEVANT_THRESHOLD = 0.5  # 滑动窗口：旧 block 的事件仍与最新 block 相关的最低置信度

# 表情包判定的常量
STICKER_CONTEXT_MESSAGES = 5  # 提交给 Jev 的最近聊天消息条数
STICKER_MIN_CONFIDENCE = 0.6  # 选表情包的置信度低于该值时不发送

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
    favor_message: str = ""  # 触发这次评价的消息原文（用于重复消息门控与落库）
    favor_confidence: float = 0.0  # Jev 对 favor_score 的置信度（0-1）
    reply_required: bool = False

    @property
    def favor_changed(self) -> bool:
        return bool(self.favor_target) and self.favor_score != 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _score_level(answer: ScoreAnswer, levels: int) -> int:
    """把连续的 score 收敛到 [0, levels-1] 的等级下标"""
    return int(_clamp(round(answer.score), 0, levels - 1))


def _get_private_target(session: Any) -> Optional[str]:
    """私聊会话中唯一的对话者昵称；群聊返回 None

    私聊只有一个人，好感度评价的对象是确定的，因此不必再让 Jev 去挑人。
    昵称优先取 ``PrivateSession.nickname``（setup 时已解析），拿不到时退回
    消息缓存中唯一的非自身昵称。
    """
    try:
        if session.get_session_type() != "private":
            return None
    except Exception:
        return None
    nickname = getattr(session, "nickname", "") or ""
    if nickname:
        return nickname
    others = {message.get("nickname") or "" for message in session.cached_messages if not message.get("self")}
    others.discard("")
    if len(others) == 1:
        return others.pop()
    return None


def _get_latest_message_text(session: Any, nickname: str) -> str:
    """取会话缓存里该用户最新的一条消息原文

    好感度评价的对象是「这一轮之前用户说的话」，消息缓存按时间正序排列，
    因此从后往前找第一条属于该昵称、内容非空的消息。同一条消息被反复发送时，
    后续的门控（``utils/fav_judge.py``）会据此抬高置信度要求。
    """
    for message in reversed(session.cached_messages):
        if message.get("self"):
            continue
        if (message.get("nickname") or "") != nickname:
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content
    return ""


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

    # 私聊里只有一位对话者，不存在「评价谁」的问题：不再向 Jev 提问 favor_target，
    # 直接把他作为被评价对象，只保留 favor_score 的判定。
    private_target = _get_private_target(session)

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
        if private_target is None:
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

    # 私聊没有 favor_target 答案，被评价对象直接取会话中的唯一对话者
    target_answer = answers.get("favor_target")
    score_answer = answers.get("favor_score")
    if private_target is not None:
        favor_target_name: Optional[str] = private_target
    elif isinstance(target_answer, ChoiceAnswer) and target_answer.choice in participants:
        favor_target_name = target_answer.choice
    else:
        favor_target_name = None
    if favor_target_name is not None and isinstance(score_answer, ChoiceAnswer):
        try:
            score_value = int(score_answer.choice)
        except ValueError:
            score_value = 0
        if score_value != 0:
            evaluation.favor_target = favor_target_name
            evaluation.favor_score = score_value
            evaluation.favor_confidence = score_answer.confidence
            evaluation.favor_message = _get_latest_message_text(session, favor_target_name)
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
            evaluation.favor_message,
            evaluation.favor_confidence,
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


@dataclass
class StickerSelection:
    """一次 send_sticker 的 Jev 判定结果

    - ``send``：Jev 选出了要发送的表情包，``sticker_id`` 有效
    - ``declined``：Jev 明确决定不发送（选了 none）
    - ``low_confidence``：选中的结果置信度过低，不发送
    - ``skipped``：Jev 不可用或未取得有效答案，不发送
    """

    status: Literal["send", "declined", "low_confidence", "skipped"]
    sticker_id: Optional[int] = None  # 要发送的表情包；仅 status 为 send 时保证有效
    description: str = ""  # 选中表情包的描述（用于回复 Chat 模型）
    confidence: float = 0.0  # Jev 对选择结果的置信度（0-1）


def _describe_sticker(sticker: Any) -> str:
    """生成候选表情包的一句话描述，作为 Jev choice 问题里该选项的 criteria 文本"""
    parts = []
    description = str(getattr(sticker, "description", "") or "").strip()
    if description:
        parts.append(description)
    meme_text = str(getattr(sticker, "meme_text", "") or "").strip()
    if meme_text:
        parts.append(f"图内文字：{meme_text}")
    emotion = str(getattr(sticker, "emotion", "") or "").strip()
    if emotion:
        parts.append(f"情绪：{emotion}")
    return "；".join(parts) or f"id: {getattr(sticker, 'id', '?')}"


def _get_thinking_content(processor: "MessageProcessor") -> str:
    """读取 Moonlark 当前的思考内容，作为 Jev 的辅助参考

    工具调用发生在本轮 LLM 请求内部，优先从进行中的请求消息里取最新的
    reasoning_content；请求尚未产生思考内容时退回上一轮的缓存。
    """
    try:
        messages = processor.openai_messages.fetcher.session.messages
    except Exception:
        messages = []
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") not in ("assistant", None):
            continue
        reasoning = _extract_reasoning(message)
        if reasoning:
            return reasoning
    return getattr(processor, "_latest_reasioning_content_cache", "") or ""


async def select_sticker(
    processor: "MessageProcessor",
    query: str,
    candidates: Sequence[Any],
) -> StickerSelection:
    """根据请求关键词，让 Jev 从候选表情包中选出要发送的一个

    判定以 ``requested_keyword``（Chat 模型请求的关键词）为主，
    最近的聊天消息与 Moonlark 的思考内容仅作辅助参考。
    Jev 可以通过选择 none 决定不发送；置信度过低时同样不发送。

    Args:
        processor: 当前会话的处理器
        query: Chat 模型请求的表情包关键词
        candidates: 在数据库中搜索得到的候选 Sticker 列表（非空）

    Returns:
        判定结果：status 为 send 时携带选中的 sticker_id，其余状态均不发送
    """
    local_str = processor.session.lang_str

    if not candidates:
        return StickerSelection(status="skipped")

    state = {
        "requested_keyword": query,
        "chat_context": await processor.session.get_cached_messages_string(
            length=STICKER_CONTEXT_MESSAGES, include_self_message=True
        ),
        "thinking_content": _get_thinking_content(processor),
    }

    criteria = {str(sticker.id): _describe_sticker(sticker) for sticker in candidates}
    criteria["none"] = lang_ref("sticker.none")
    questions: dict[str, Question] = {
        "pick": choice(lang_ref("sticker.instructions"), criteria=criteria),
    }

    try:
        answers = await ask(state, questions, lang_str=local_str, identify="Sticker Selection")
    except Exception as e:
        _log_jev_failure("表情包判定", processor.session.session_id, e)
        return StickerSelection(status="skipped")
    if not answers:
        logger.warning(f"[JevJudge:{processor.session.session_id}] 表情包判定没有取得任何答案")
        return StickerSelection(status="skipped")

    answer = answers.get("pick")
    if not isinstance(answer, ChoiceAnswer):
        return StickerSelection(status="skipped")

    # Jev 选择 none：明确决定不发送
    if answer.choice == "none":
        logger.debug(
            f"[JevJudge:{processor.session.session_id}] 表情包判定选择不发送 (confidence={answer.confidence:.0%})"
        )
        return StickerSelection(status="declined", confidence=answer.confidence)

    # 把选择题的答案键还原成候选表情包的数据库 ID
    try:
        sticker_id = int(answer.choice)
    except ValueError:
        return StickerSelection(status="skipped", confidence=answer.confidence)
    matched = next((sticker for sticker in candidates if sticker.id == sticker_id), None)
    if matched is None:
        return StickerSelection(status="skipped", confidence=answer.confidence)

    if answer.confidence < STICKER_MIN_CONFIDENCE:
        logger.debug(
            f"[JevJudge:{processor.session.session_id}] 表情包 {sticker_id} 置信度过低，"
            f"不发送 ({answer.confidence:.0%} < {STICKER_MIN_CONFIDENCE:.0%})"
        )
        return StickerSelection(status="low_confidence", sticker_id=sticker_id, confidence=answer.confidence)

    return StickerSelection(
        status="send",
        sticker_id=sticker_id,
        description=_describe_sticker(matched),
        confidence=answer.confidence,
    )
