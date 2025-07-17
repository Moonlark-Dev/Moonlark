from typing import cast
from datetime import datetime, timezone

from nonebot import on_message
from nonebot.adapters import Event, Bot
from nonebot.rule import Rule
from nonebot_plugin_alconna import Image, Text, UniMessage, image_fetch
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id, is_private_message
from nonebot_plugin_larkuser import prompt
from nonebot_plugin_larkcave.decoder import decode_cave
from nonebot_plugin_larkcave.models import CaveData
from nonebot_plugin_larkcave.plugins.add.__main__ import get_cave_id
from nonebot_plugin_larkcave.plugins.add.checker import check_cave
from nonebot_plugin_larkcave.plugins.add.encoder import encode_image
from nonebot_plugin_larkcave.plugins.add.exception import (
    DuplicateCave,
    EmptyImage,
    ReviewFailed,
)
from nonebot_plugin_orm import async_scoped_session

lang = LangHelper()


def is_single_image_message(event: Event) -> bool:
    """检查消息是否只包含一张图片"""
    try:
        message = UniMessage.generate_without_reply(event=event)
        
        # 统计图片和文本数量
        image_count = 0
        text_content = ""
        
        for segment in message:
            if isinstance(segment, Image):
                image_count += 1
            elif isinstance(segment, Text):
                # 去除空白字符检查是否有实际文本内容
                text_content += segment.text.strip()
        
        # 只有一张图片且没有文本内容
        if image_count == 1 and not text_content:
            return True
    except Exception:
        from nonebot.log import logger
        logger.debug("Failed to check if message is single image", exc_info=True)
    return False


async def ask_cave_submission(user_id: str) -> bool:
    """询问用户是否要投稿到 Cave"""
    try:
        # Get translated responses
        yes_text = await lang.text("yes", user_id)
        no_text = await lang.text("no", user_id)
        
        def checker(text: str) -> bool:
            text_lower = text.strip().lower()
            text_original = text.strip()
            # Support translated responses and English shortcuts
            return (text_original == yes_text or 
                    text_original == no_text or
                    text_lower in ['y', 'yes', 'n', 'no'])
        
        response = await prompt(
            UniMessage.text(await lang.text("ask", user_id)),
            user_id,
            checker=checker,
            timeout=60,
            allow_quit=False
        )
        
        # Check if response is positive
        response_lower = response.strip().lower()
        response_original = response.strip()
        return (response_original == yes_text or 
                response_lower in ['y', 'yes'])
    except Exception:
        return False


# 监听私聊中的单图片消息
image_prompt = on_message(
    Rule(is_private_message) & Rule(is_single_image_message),
    priority=9,
    block=True,
)


@image_prompt.handle()
async def handle_image_prompt(event: Event, user_id: str = get_user_id()) -> None:
    """处理单图片消息，询问是否投稿到 Cave"""
    try:
        message = UniMessage.generate_without_reply(event=event)
        
        # 找到图片
        image = None
        for segment in message:
            if isinstance(segment, Image):
                image = segment
                break
        
        if not image:
            return
        
        # 询问用户是否要投稿
        if await ask_cave_submission(user_id):
            # 用户确认投稿，调用 Cave 的 add 功能
            
            # 构造 Cave add 命令的参数
            content = [image]
            
            # 模拟 cave add 命令调用
            await lang.send("submitting", user_id)
            
            # 使用 Cave 插件的 add 功能
            try:
                # 获取当前的 bot 和 session
                bot = cast("Bot", event.get_bot())
                
                async with async_scoped_session() as session:
                    # 检查内容
                    state = {}
                    await check_cave(content, event, bot, state, session)
                    
                    # 获取新的 Cave ID
                    cave_id = await get_cave_id(session)
                    
                    # 编码图片
                    image_bytes = cast("bytes", await image_fetch(event, bot, state, image))
                    encoded_content = await encode_image(cave_id, image.name, image_bytes, session)
                    
                    # 保存到数据库
                    session.add(CaveData(
                        id=cave_id,
                        author=user_id,
                        time=datetime.now(timezone.utc),
                        content=encoded_content,
                    ))
                    await session.commit()
                    
                    await lang.finish("success", user_id, cave_id)
                    
            except ReviewFailed as e:
                await lang.finish("error", user_id, f"内容审核失败: {e.reason}")
            except EmptyImage:
                await lang.finish("error", user_id, "图片获取失败")
            except DuplicateCave as e:
                # 构建相似洞穴信息
                async with async_scoped_session() as session:
                    from nonebot_plugin_alconna import Text
                    msg = UniMessage(await lang.text("error", user_id, "发现相似的回声洞"))
                    msg.extend(await decode_cave(e.cave, session, user_id))
                    msg.append(Text(f"\n相似度: {round(e.score * 100, 3)}%"))
                    await image_prompt.finish(msg)
                    
            except Exception as e:
                # 如果出错，发送错误信息
                await lang.finish("error", user_id, str(e))
        else:
            # 用户选择不投稿或超时
            await lang.finish("cancelled", user_id)
            
    except Exception:
        # 静默失败，不干扰正常消息处理，但记录到日志以便调试
        from nonebot.log import logger
        logger.debug("Cave image prompt failed silently", exc_info=True)