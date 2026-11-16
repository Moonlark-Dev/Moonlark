"""Chat 的模型 Provider 选择

Chat 的主模型可以在 OpenAI 与 Gemini 两套 SDK 之间切换，Provider 分两层：

- 全局默认：保存在 ``ChatGlobalSetting`` 的 ``model_provider`` 键中，由超级用户通过
  ``/chat model <openai|gemini>`` 修改，所有没有单独设置的会话共用；
- 分会话设置：保存在 ``ChatSessionSetting`` 的 ``(session_id, model_provider)`` 中，
  由 ``/chat model <openai|gemini> <session_id>`` 设置，用
  ``/chat model default [session_id]`` 恢复成跟随全局默认。

:func:`get_model_provider` 带 ``session_id`` 时先读分会话设置、没有再回落到全局默认；
不带 ``session_id`` 时只读全局默认。这里只影响 Chat 主模型（``MessageProcessor`` /
``MessageQueue`` 的会话请求）；Ask AI、Decision 判定、笔记整理、Image Describe 等其它
调用仍使用各自插件配置的模型。

除主模型外，Gemini 模式下还有两处行为随之变化（见 ``core/message.py`` 与
``core/processor.py``）：provider 缓存过期后触发 block 选择的时间缩短到 5 分钟，
System Prompt 同时声明内嵌图片与「图片被拦截后替换为文字描述」两种图片格式。
"""

from typing import Literal, Optional

from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select

from ..models import ChatGlobalSetting, ChatSessionSetting

ModelProvider = Literal["openai", "gemini"]

# 全局设置表与会话设置表中保存 Provider 的键名
PROVIDER_SETTING_KEY = "model_provider"
DEFAULT_PROVIDER: ModelProvider = "openai"
VALID_PROVIDERS: tuple[ModelProvider, ...] = ("openai", "gemini")
# 距离上次请求超过该时长才认为 provider 前缀缓存过期，进而触发 block 选择
# （ChatContext.run_sliding_window）。OpenAI 的缓存约 10 分钟过期；Gemini 只有 5 分钟，
# 缓存过期后历史 block 的命中率明显下降，因此 Gemini 模式下更早做清理。
OPENAI_SLIDING_WINDOW_IDLE_SECONDS = 600
GEMINI_SLIDING_WINDOW_IDLE_SECONDS = 300


def normalize_provider(value: str) -> Optional[ModelProvider]:
    """把用户输入规范化成 Provider 名；非法值返回 None"""
    normalized = value.strip().lower()
    if normalized in VALID_PROVIDERS:
        return normalized  # type: ignore[return-value]
    return None


def is_default_provider(value: str) -> bool:
    """用户输入是否为恢复默认的保留值 ``default``（也接受写法 ``:default:``）"""
    return value.strip().strip(":").lower() == "default"


async def get_global_model_provider() -> ModelProvider:
    """读取全局默认 Provider，未设置或值非法时回落到 openai"""
    async with get_session() as session:
        setting = await session.get(ChatGlobalSetting, {"key": PROVIDER_SETTING_KEY})
    if setting is None:
        return DEFAULT_PROVIDER
    return normalize_provider(setting.value) or DEFAULT_PROVIDER


async def set_global_model_provider(provider: ModelProvider) -> None:
    """更新全局默认 Provider"""
    async with get_session() as session:
        setting = await session.get(ChatGlobalSetting, {"key": PROVIDER_SETTING_KEY})
        if setting is None:
            await session.merge(ChatGlobalSetting(key=PROVIDER_SETTING_KEY, value=provider))
        else:
            setting.value = provider
            await session.merge(setting)
        await session.commit()


async def reset_global_model_provider() -> None:
    """删除全局默认 Provider，让它回到 ``DEFAULT_PROVIDER``"""
    async with get_session() as session:
        await session.execute(delete(ChatGlobalSetting).where(ChatGlobalSetting.key == PROVIDER_SETTING_KEY))
        await session.commit()


async def get_session_model_provider(session_id: str) -> Optional[ModelProvider]:
    """读取单个会话单独设置的 Provider；没有设置或值非法时返回 None（跟随全局）"""
    if not session_id:
        return None
    async with get_session() as db_session:
        setting = await db_session.get(
            ChatSessionSetting,
            {"session_id": session_id, "key": PROVIDER_SETTING_KEY},
        )
    if setting is None:
        return None
    return normalize_provider(setting.value)


async def set_session_model_provider(session_id: str, provider: ModelProvider) -> None:
    """为单个会话设置 Provider"""
    async with get_session() as session:
        setting = await session.get(
            ChatSessionSetting,
            {"session_id": session_id, "key": PROVIDER_SETTING_KEY},
        )
        if setting is None:
            await session.merge(ChatSessionSetting(session_id=session_id, key=PROVIDER_SETTING_KEY, value=provider))
        else:
            setting.value = provider
            await session.merge(setting)
        await session.commit()


async def clear_session_model_provider(session_id: str) -> bool:
    """删除会话的 Provider 设置，让它重新跟随全局默认；返回是否真的删掉了记录"""
    async with get_session() as session:
        setting = await session.get(
            ChatSessionSetting,
            {"session_id": session_id, "key": PROVIDER_SETTING_KEY},
        )
        if setting is None:
            return False
        await session.delete(setting)
        await session.commit()
        return True


async def list_session_model_providers() -> dict[str, ModelProvider]:
    """列出所有单独设置的会话及其 Provider（按会话 ID 排序，忽略非法值）"""
    async with get_session() as session:
        rows = (
            await session.scalars(
                select(ChatSessionSetting).where(ChatSessionSetting.key == PROVIDER_SETTING_KEY),
            )
        ).all()
    providers: dict[str, ModelProvider] = {}
    for row in rows:
        provider = normalize_provider(row.value)
        if provider is not None:
            providers[row.session_id] = provider
    return dict(sorted(providers.items()))


async def get_model_provider(session_id: Optional[str] = None) -> ModelProvider:
    """读取 Provider：带 ``session_id`` 时优先用该会话的设置，否则用全局默认"""
    if session_id:
        provider = await get_session_model_provider(session_id)
        if provider is not None:
            return provider
    return await get_global_model_provider()


async def get_sliding_window_idle_seconds(session_id: Optional[str] = None) -> float:
    """当前 Provider 对应的 block 选择等待时长（秒）"""
    provider = await get_model_provider(session_id)
    if provider == "gemini":
        return GEMINI_SLIDING_WINDOW_IDLE_SECONDS
    return OPENAI_SLIDING_WINDOW_IDLE_SECONDS
