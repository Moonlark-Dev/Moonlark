"""群 QQ 号与群聊 openid 绑定功能"""

import re
import random
import string
from datetime import datetime, timezone

from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters import Bot, Event
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkutils import get_group_id, get_user_id

from .config import config
from .models import GroupBind

# 绑定验证码的正则模式
BIND_CODE_PATTERN = re.compile(r"\[MoonlarkBind:([A-Za-z0-9]{8})\]")

# 验证码长度
BIND_CODE_LENGTH = 8


def generate_bind_code() -> str:
    """生成一个随机的绑定验证码"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=BIND_CODE_LENGTH))


def format_bind_message(code: str) -> str:
    """格式化绑定消息"""
    return f"[MoonlarkBind:{code}]"


async def get_group_id_from_event(bot: Bot, event: Event) -> str | None:
    """从事件中提取群 ID（OB11 用 QQ 号，QQ 官方 bot 用 openid）"""
    try:
        if isinstance(bot, V11Bot):
            # onebot 11: group_id 已经是 QQ 群号格式
            group_id = event.get_session_id()
            # 格式: onebot_v11_{qq_number}
            if group_id:
                parts = group_id.rsplit("_", 1)
                if len(parts) == 2:
                    return parts[1]
        elif isinstance(bot, QQBot):
            # QQ 官方 bot: group_openid
            if hasattr(event, "group_openid"):
                return event.group_openid
    except Exception as e:
        logger.warning(f"获取群 ID 失败: {e}")
    return None


async def try_process_bind_code(bot: Bot, event: Event, session_id: str) -> bool:
    """
    检测并处理绑定验证码。

    当任何 bot 检测到消息中含有绑定验证码时，尝试完成绑定。

    返回 True 表示已处理绑定（应阻断后续处理），False 表示未检测到绑定码。
    """
    try:
        message = event.get_plaintext()
    except Exception:
        return False

    match = BIND_CODE_PATTERN.search(message)
    if not match:
        return False

    code = match.group(1)
    logger.info(f"[Bind] 检测到绑定验证码: {code}")

    async with get_session() as session:
        # 查找绑定了此验证码的记录
        from sqlalchemy import select

        result = await session.execute(select(GroupBind).where(GroupBind.bind_code == code))
        bind_record = result.scalar_one_or_none()

        if bind_record is None:
            logger.warning(f"[Bind] 未找到验证码 {code} 对应的绑定记录")
            return True  # 仍然阻断，避免传播到其他 handler

        # 检查验证码是否过期
        if bind_record.bind_code_created_at is not None:
            elapsed = (
                datetime.now(timezone.utc) - bind_record.bind_code_created_at.replace(tzinfo=timezone.utc)
            ).total_seconds()
            if elapsed > config.bots_bind_group_timeout:
                logger.info(f"[Bind] 验证码 {code} 已过期 ({elapsed:.0f}s > {config.bots_bind_group_timeout}s)")
                return True  # 过期，阻断消息

        # 根据 bot 类型补全绑定信息
        if isinstance(bot, V11Bot):
            # OB11 bot 看到 QQ bot 发出的绑定码消息
            # 补全 group_qq_number
            group_qq = await get_group_id_from_event(bot, event)
            if group_qq:
                bind_record.group_qq_number = group_qq
                logger.info(f"[Bind] OB11 补全群 QQ 号: {group_qq}")
        elif isinstance(bot, QQBot):
            # QQ bot 看到 OB11 发出的绑定码消息
            # 补全 group_openid
            group_oid = await get_group_id_from_event(bot, event)
            if group_oid:
                bind_record.group_openid = group_oid
                logger.info(f"[Bind] QQBot 补全群 openid: {group_oid}")

        # 检查是否两端都已填写（绑定完成）
        if bind_record.group_qq_number and bind_record.group_openid:
            bind_record.bound_at = datetime.now(timezone.utc)
            bind_record.bind_code = None  # 清除验证码
            logger.info(f"[Bind] 群绑定完成: QQ号={bind_record.group_qq_number} <-> openid={bind_record.group_openid}")
        else:
            logger.info(f"[Bind] 绑定信息补全中: QQ号={bind_record.group_qq_number}, openid={bind_record.group_openid}")

        await session.commit()

    return True  # 阻断消息传播


# 绑定命令
bind_group = on_command("bind-group-id", priority=1, block=True)


@bind_group.handle()
async def handle_bind_group_id(bot: Bot, event: Event) -> None:
    """处理 /bind-group-id 命令"""
    code = generate_bind_code()
    now = datetime.now(timezone.utc)

    async with get_session() as session:
        from sqlalchemy import select

        if isinstance(bot, V11Bot):
            group_qq = await get_group_id_from_event(bot, event)
            if not group_qq:
                await bind_group.finish("无法获取群 QQ 号，请稍后再试")

            # 检查是否已有绑定记录（通过 group_qq_number 查找）
            result = await session.execute(select(GroupBind).where(GroupBind.group_qq_number == group_qq))
            existing = result.scalar_one_or_none()

            if existing:
                # 更新验证码
                existing.bind_code = code
                existing.bind_code_created_at = now
                existing.group_openid = None  # 重置 openid，需要重新绑定
                existing.bound_at = None
                logger.info(f"[Bind] 重置群 {group_qq} 的绑定验证码")
            else:
                bind_record = GroupBind(
                    group_qq_number=group_qq,
                    bind_code=code,
                    bind_code_created_at=now,
                )
                session.add(bind_record)
                logger.info(f"[Bind] 创建群 {group_qq} 的绑定记录")

            await session.commit()

        elif isinstance(bot, QQBot):
            group_oid = await get_group_id_from_event(bot, event)
            if not group_oid:
                await bind_group.finish("无法获取群 openid，请稍后再试")

            # QQ bot 发起的绑定：检查是否已有记录
            result = await session.execute(select(GroupBind).where(GroupBind.group_openid == group_oid))
            existing = result.scalar_one_or_none()

            if existing:
                existing.bind_code = code
                existing.bind_code_created_at = now
                existing.bound_at = None
                logger.info(f"[Bind] 重置群 openid={group_oid} 的绑定验证码")
            else:
                bind_record = GroupBind(
                    group_openid=group_oid,
                    bind_code=code,
                    bind_code_created_at=now,
                )
                session.add(bind_record)
                logger.info(f"[Bind] QQBot 创建群 openid={group_oid} 的绑定记录")

            await session.commit()

        else:
            await bind_group.finish("当前 bot 类型不支持群绑定")
            return

    # 发送绑定验证码
    bind_msg = format_bind_message(code)
    await bind_group.finish(f"群绑定验证码已生成，请等待另一个 bot 识别完成：\n{bind_msg}")
