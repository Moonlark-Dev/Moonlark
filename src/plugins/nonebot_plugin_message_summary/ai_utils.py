import json
from typing import Sequence
from datetime import datetime, timedelta, timezone
from nonebot import logger
from nonebot_plugin_openai import fetch_message, generate_message
from .lang import lang
from .models import GroupMessage, CatGirlScore, DebateAnalysis


async def generate_message_string(result: list[GroupMessage] | Sequence[GroupMessage], style: str) -> str:
    messages = ""
    for message in list(result)[::-1]:
        if style in ["broadcast", "bc"]:
            # Format timestamp to include both date and time for broadcast style
            timestamp_str = message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            messages += f"[{timestamp_str}] [{message.sender_nickname}] {message.message}\n"
        else:
            messages += f"[{message.sender_nickname}] {message.message}\n"
    return messages


async def fetch_broadcast_summary(user_id: str, messages: str) -> str:
    time_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    summary_string = await fetch_message(
        [
            generate_message(await lang.text("prompt2s", user_id, time_str), "system"),
            generate_message(await lang.text("prompt2u", user_id, messages), "user"),
        ],
        identify="Message Summary (Broadcast)",
    )
    return summary_string


async def fetch_default_summary(user_id: str, messages: str) -> str:
    summary_string = await fetch_message(
        [generate_message(await lang.text("prompt", user_id), "system"), generate_message(messages, "user")],
        identify="Message Summary",
    )
    return summary_string


async def fetch_topic_summary(user_id: str, messages: str) -> str:
    summary_string = await fetch_message(
        [generate_message(await lang.text("prompt_topic", user_id), "system"), generate_message(messages, "user")],
        identify="Message Summary (Topic)",
    )
    return summary_string


async def fetch_daily_summary(user_id: str, messages: str) -> str:
    summary_string = await fetch_message(
        [
            generate_message(await lang.text("prompt_everyday_summary", user_id, datetime.now().isoformat()), "system"),
            generate_message(messages, "user"),
        ],
        identify="Message Summary (Daily)",
    )
    return summary_string


async def get_catgirl_score(message_list: str) -> list[CatGirlScore]:
    """获取由聊天记录总结出来的猫娘分数"""
    return json.loads(
        await fetch_message(
            [
                generate_message(await lang.text("neko.prompt", message_list), "system"),
                generate_message(message_list, "user"),
            ],
            identify="Message Summary (Neko)",
        )
    )


async def analyze_debate(messages: str, user_id: str) -> DebateAnalysis | None:
    """分析聊天记录中的辩论内容"""
    result = await fetch_message(
        [
            generate_message(await lang.text("debate.prompt", user_id), "system"),
            generate_message(messages, "user"),
        ],
        identify="Message Summary (Debate)",
    )

    # 检查是否检测到冲突
    if "NO_CONFLICT_DETECTED" in result:
        return None

    # 清理 JSON 字符串
    result = result.strip()
    if result.startswith("```json"):
        result = result[7:]
    if result.endswith("```"):
        result = result[:-3]
    result = result.strip()

    return json.loads(result)


async def generate_semantic_search_payload(query: str) -> str:
    """Stage 1: Intent Extraction"""
    prompt = await lang.text("check_history.prompt_stage1", "")
    result = await fetch_message(
        [
            generate_message(prompt, "system"),
            generate_message(query, "user"),
        ],
        identify="Message Summary (History Check Stage 1)",
    )
    return result.strip()


async def analyze_history(payload: str, history: list[GroupMessage], user_id: str) -> dict | None:
    """Stage 2: Historical Analysis"""
    messages_str = await generate_message_string(history, "broadcast")
    prompt = await lang.text("check_history.prompt_stage2", user_id)

    result = await fetch_message(
        [
            generate_message(prompt, "system"),
            generate_message(f"Payload: {payload}\n\nHistory:\n{messages_str}", "user"),
        ],
        identify="Message Summary (History Check Stage 2)",
    )

    if "NO_MATCH_FOUND" in result:
        return None

    # Clean JSON string
    result = result.strip()
    if result.startswith("```json"):
        result = result[7:]
    if result.endswith("```"):
        result = result[:-3]
    result = result.strip()

    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        logger.exception(e)
        return None
