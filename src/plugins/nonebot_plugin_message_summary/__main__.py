from datetime import datetime, timedelta

from nonebot import get_bots, logger
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_bots.models import GroupBind
from nonebot_plugin_broadcast import get_available_groups
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkutils import FileType, open_file
from nonebot_plugin_larkutils.command import get_command_prefix
from nonebot_plugin_larkutils.file import FileManager
from nonebot_plugin_openai import fetch_message, generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .ai_utils import extract_mvp_from_summary, generate_message_string
from .lang import lang
from .models import GroupMessage, GroupDailySummary, MVPRecord

# This file is kept for backward compatibility and scheduler tasks
# Most logic has been moved to matcher.py, ai_utils.py, render_utils.py

# 每日总结定时推送的时刻。群内只剩 QQ 适配器 Bot 可用时，无法主动推送，
# 改为在该时刻之后由当天收到的第一条消息触发（见 try_send_qq_daily_summary）。
DAILY_SUMMARY_HOUR = 6

# 正在生成/发送每日总结的群，避免同一群内的并发消息重复触发
_qq_daily_summary_pending: set[str] = set()


def get_everyday_summary_config() -> FileManager:
    """Get the config file for everyday summary feature"""
    return open_file("everyday_summary_config.json", FileType.CONFIG, [])


def get_daily_summary_state() -> FileManager[dict[str, str]]:
    """读取「各群最近一次每日总结推送日期」的状态文件"""
    return open_file("daily_summary_state.json", FileType.CONFIG, {})


def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def daily_state_key(group_id: str, bound_qq_number: str | None = None) -> str:
    """同一个物理群在 OB11 / QQ 适配器下共用的状态键

    QQ 官方的 group_openid 若已绑定群号，则统一用群号记录推送状态，
    这样同一个群不会因为两条链路各推送一次。
    """
    return f"qq_{bound_qq_number}" if bound_qq_number else group_id


async def get_bound_qq_number(group_openid: str) -> str | None:
    """获取 QQ 群 openid 绑定的 OneBot 群号，未绑定时返回 None"""
    async with get_session() as session:
        bind = await session.scalar(select(GroupBind).where(GroupBind.group_openid == group_openid))
    return bind.group_qq_number if bind is not None else None


async def resolve_state_key(group_id: str) -> str:
    """把群标识归一化为推送状态键（按 GroupBind 把 openid 换成群号）"""
    raw = group_id.removeprefix("qq_")
    if raw.isdigit():
        return group_id
    return daily_state_key(group_id, await get_bound_qq_number(raw))


async def is_daily_summary_enabled(*group_keys: str) -> bool:
    """判断这些群标识中是否有任意一个开启了每日总结推送"""
    async with get_everyday_summary_config() as config:
        return any(key in config.data for key in group_keys)


async def is_daily_summary_sent(state_key: str) -> bool:
    """该群今天是否已经推送过每日总结"""
    async with get_daily_summary_state() as state:
        return state.data.get(state_key) == today_key()


async def mark_daily_summary_sent(state_key: str) -> None:
    """记录今天已推送

    6:00 之前的推送不算数：用户凌晨手动查看不应导致当天的自动推送被跳过。
    """
    if datetime.now().hour < DAILY_SUMMARY_HOUR:
        return
    async with get_daily_summary_state() as state:
        state.data[state_key] = today_key()


async def is_ob11_group_available(group_qq_number: str) -> bool:
    """群内是否至少有一个能看到该群的 OneBot V11 bot"""
    for bot in get_bots().values():
        if not isinstance(bot, V11Bot):
            continue
        try:
            group_list = await bot.get_group_list()
        except Exception as e:
            logger.warning(f"获取 {bot.self_id} 的群列表失败: {e}")
            continue
        if group_qq_number in {str(group["group_id"]) for group in group_list}:
            return True
    return False


def is_group_daily_invocation(event: Event) -> bool:
    """消息本身是否为 group-daily 指令

    指令处理器会自行发送总结，自动推送需要让位，避免同一条消息推送两次。
    """
    text = event.get_plaintext().strip()
    prefix = get_command_prefix()
    if prefix:
        if not text.startswith(prefix):
            return False
        text = text[len(prefix) :].lstrip()
    return text.startswith("group-daily")


async def get_cached_daily_summary(group_id: str) -> str | None:
    """Get cached daily summary for a group if it exists for today"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_session() as session:
        record = await session.get(GroupDailySummary, {"group_id": group_id, "date": today})
        return record.summary if record else None


async def update_mvp_records(group_id: str, summary_string: str, start_time: datetime, end_time: datetime) -> None:
    """根据总结中选出的 MVP 更新 MVP 排行榜"""
    mvp_data = await extract_mvp_from_summary(summary_string)
    if not mvp_data:
        return
    mvp_nickname, _ = mvp_data
    async with get_session() as session:
        mvp_result = await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.timestamp >= start_time)
            .where(GroupMessage.timestamp <= end_time)
            .where(GroupMessage.sender_nickname == mvp_nickname),
        )
        mvp_message = mvp_result.first()
        if mvp_message and mvp_message.user_id:
            mvp_record = await session.get(MVPRecord, {"user_id": mvp_message.user_id, "group_id": group_id})
            if mvp_record:
                mvp_record.mvp_count += 1
            else:
                session.add(MVPRecord(user_id=mvp_message.user_id, group_id=group_id, mvp_count=1))
            await session.commit()


async def generate_daily_summary(group_id: str) -> str | None:
    """生成当日群聊总结并写入缓存

    统计范围是最近 24 小时；群内没有消息时返回 None，调用方不应推送。
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1)

    async with get_session() as session:
        result = await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.timestamp >= start_time)
            .where(GroupMessage.timestamp <= end_time)
            .order_by(GroupMessage.id_),
        )
        messages = list(result.all())[::-1]

        if not messages:
            return None

        messages_str = await generate_message_string(list(messages), "broadcast")
        user_id = messages[0].sender_nickname

    summary_string = await fetch_message(
        [
            generate_message(await lang.text("prompt_everyday_summary", user_id, datetime.now().isoformat()), "system"),
            generate_message(messages_str, "user"),
        ],
        identify="Message Summary (Daily)",
    )

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_session() as session:
        existing = await session.get(GroupDailySummary, {"group_id": group_id, "date": today})
        if existing:
            existing.summary = summary_string
        else:
            session.add(GroupDailySummary(group_id=group_id, date=today, summary=summary_string))
        await session.commit()

    await update_mvp_records(group_id, summary_string, start_time, end_time)
    return summary_string


async def send_daily_summary_to_group(group_id: str) -> None:
    """6:00 定时任务使用：通过 OneBot V11 主动推送

    只处理有可用 OB11 bot 的群聊；群内只剩 QQ 适配器 Bot 时跳过，
    由 try_send_qq_daily_summary 在收到消息时被动推送。
    """
    target_group_id = group_id.split("_", 1)[1]
    available_groups = await get_available_groups()
    bot = next((item for item in available_groups.get(target_group_id, []) if isinstance(item, V11Bot)), None)
    if bot is None:
        return

    summary_string = await generate_daily_summary(group_id)
    if summary_string is None:
        return

    try:
        image_bytes = await md_to_pic(summary_string)
        msg = await UniMessage().image(raw=image_bytes).export(bot)
        await bot.send_group_msg(group_id=int(target_group_id), message=msg)
    except Exception as e:
        logger.exception(e)
        return

    await mark_daily_summary_sent(await resolve_state_key(group_id))


async def send_daily_summary_to_qq(bot: QQBot, event: GroupMessageCreateEvent, group_id: str, state_key: str) -> None:
    """QQ 适配器使用：复用当前消息事件被动发送当日总结

    QQ 官方的主动消息受限，因此必须挂在收到的事件上发送。
    """
    summary_string = await generate_daily_summary(group_id)
    if summary_string is None:
        return

    try:
        image_bytes = await md_to_pic(summary_string)
        await UniMessage().image(raw=image_bytes).send(target=event, bot=bot)
    except Exception as e:
        logger.exception(e)
        return

    await mark_daily_summary_sent(state_key)


async def try_send_qq_daily_summary(bot: QQBot, event: GroupMessageCreateEvent, group_id: str) -> None:
    """群内只剩 QQ 适配器 Bot 可用时的每日总结推送

    在 6:00 之后收到当天第一条消息时生成并发送；每个群每天只推送一次。
    """
    if datetime.now().hour < DAILY_SUMMARY_HOUR:
        return
    if group_id in _qq_daily_summary_pending:
        return
    if is_group_daily_invocation(event):
        # 这条消息就是 group-daily 指令，交给指令处理器发送
        return

    bound_qq_number = await get_bound_qq_number(event.group_openid)
    state_key = daily_state_key(group_id, bound_qq_number)

    if not await is_daily_summary_enabled(group_id, state_key):
        return
    if await is_daily_summary_sent(state_key):
        return
    if bound_qq_number and await is_ob11_group_available(bound_qq_number):
        # 群内仍有可用的 OneBot bot，交给 6:00 定时任务推送
        return

    _qq_daily_summary_pending.add(group_id)
    try:
        await send_daily_summary_to_qq(bot, event, group_id, state_key)
    except Exception as e:
        logger.exception(e)
    finally:
        _qq_daily_summary_pending.discard(group_id)


@scheduler.scheduled_job("cron", hour=6, minute=0, id="daily_message_summary")
async def send_daily_message_summary() -> None:
    """Send daily message summary to all groups that have enabled this feature"""
    # Get the list of groups that have enabled everyday summary
    async with get_everyday_summary_config() as config:
        enabled_groups = list(config.data)

    # Send summary to each enabled group
    for group_id in enabled_groups:
        try:
            await send_daily_summary_to_group(group_id)
        except Exception as e:
            logger.exception(e)
