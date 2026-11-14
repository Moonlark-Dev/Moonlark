"""Chat 的模型 Provider 选择

Chat 的主模型可以在 OpenAI 与 Gemini 两套 SDK 之间切换，选择结果保存在
``ChatGlobalSetting`` 里（键 ``model_provider``），对整个进程生效——不是按群或按用户
设置，由超级用户通过 ``/chat model <openai|gemini>`` 修改。这里只影响 Chat 主模型
（``MessageProcessor`` / ``MessageQueue`` 的会话请求）；Ask AI、Decision 判定、笔记整理、
Image Describe 等其它调用仍使用各自插件配置的模型。

除主模型外，Gemini 模式下还有两处行为随之变化（见 ``core/message.py`` 与
``core/processor.py``）：provider 缓存过期后触发 block 选择的时间缩短到 5 分钟，
System Prompt 同时声明内嵌图片与「图片被拦截后替换为文字描述」两种图片格式。
"""

from typing import Literal, Optional

from nonebot_plugin_orm import get_session

from ..models import ChatGlobalSetting

ModelProvider = Literal["openai", "gemini"]

# 全局设置表中保存 Provider 的键名
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


async def get_model_provider() -> ModelProvider:
    """读取当前全局 Provider，未设置或值非法时回落到 openai"""
    async with get_session() as session:
        setting = await session.get(ChatGlobalSetting, {"key": PROVIDER_SETTING_KEY})
    if setting is None:
        return DEFAULT_PROVIDER
    return normalize_provider(setting.value) or DEFAULT_PROVIDER


async def get_sliding_window_idle_seconds() -> float:
    """当前 Provider 对应的 block 选择等待时长（秒）"""
    provider = await get_model_provider()
    if provider == "gemini":
        return GEMINI_SLIDING_WINDOW_IDLE_SECONDS
    return OPENAI_SLIDING_WINDOW_IDLE_SECONDS


async def set_model_provider(provider: ModelProvider) -> None:
    """更新全局 Provider"""
    async with get_session() as session:
        setting = await session.get(ChatGlobalSetting, {"key": PROVIDER_SETTING_KEY})
        if setting is None:
            await session.merge(ChatGlobalSetting(key=PROVIDER_SETTING_KEY, value=provider))
        else:
            setting.value = provider
            await session.merge(setting)
        await session.commit()
