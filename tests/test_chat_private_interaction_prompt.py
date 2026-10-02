"""私聊互动规则模板的回归测试。

需求：私聊恒定使用 ``interaction_private.md.jinja``（不受群聊 interaction_mode 影响），
群聊仍需按 passionate / silent / standard 正常选择；私聊模板允许用括号简短描述动作，
并要求对每一条消息都作出回应。
"""

import pytest


async def _render_chat_prompt(**overrides: object) -> str:
    """渲染 chat.md.jinja（插件导入必须在函数内部，见 tests/conftest.py）"""
    from nonebot_plugin_openai.utils.message import get_message_text

    kwargs: dict[str, object] = {
        "image_placeholder": True,
        "is_group_session": False,
        "is_private": True,
        "session_nickname": "小明",
        "interaction_mode": "standard",
    }
    kwargs.update(overrides)
    return await get_message_text("chat.md.jinja", **kwargs)


@pytest.mark.asyncio
async def test_private_session_uses_private_interaction_prompt() -> None:
    """私聊必须加载私聊专用互动规则，而不是任何群聊模式"""
    text = await _render_chat_prompt()

    assert "当前处于「私聊」场景" in text
    assert "热情模式" not in text
    assert "安静模式" not in text
    assert "以一只旁观的猫娘" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["passionate", "silent", "standard"])
async def test_private_session_ignores_group_interaction_mode(mode: str) -> None:
    """群聊互动模式不应影响私聊的互动规则选择"""
    text = await _render_chat_prompt(interaction_mode=mode)

    assert "当前处于「私聊」场景" in text
    assert "热情模式" not in text
    assert "安静模式" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "marker"),
    [
        ("passionate", "热情模式"),
        ("silent", "安静模式"),
        ("standard", "即使没有人@你"),
    ],
)
async def test_group_session_still_follows_interaction_mode(mode: str, marker: str) -> None:
    """群聊仍按 interaction_mode 选择互动规则"""
    text = await _render_chat_prompt(is_group_session=True, is_private=False, interaction_mode=mode)

    assert marker in text
    assert "当前处于「私聊」场景" not in text


@pytest.mark.asyncio
async def test_private_prompt_allows_bracketed_actions() -> None:
    """私聊模板放开括号动作描写，并删除原来的禁止条款"""
    text = await _render_chat_prompt()

    assert "允许用括号简短地描述自己的动作" in text
    assert "除非接到明确的要求，不要在消息中描述你的动作" not in text


@pytest.mark.asyncio
async def test_private_prompt_requires_reply_and_favorability_gate() -> None:
    """私聊模板要求必须回复，并保留好感度对亲密程度的限制"""
    text = await _render_chat_prompt()

    assert "每一条消息都必须得到回应" in text
    assert "私聊中可以更亲密，但程度依然由好感度决定" in text
    # 好感度细则需要被真实展开（include 生效）
    assert "好感度以整数形式表现" in text


@pytest.mark.asyncio
async def test_private_prompt_does_not_mention_group_only_tools() -> None:
    """私聊不消耗 Token，不应引导模型调用仅群聊可用的 apply_unlimited_tokens"""
    text = await _render_chat_prompt()

    assert "apply_unlimited_tokens" not in text


@pytest.mark.asyncio
async def test_favorability_table_uses_private_wording_in_private_chat() -> None:
    """共享的 favorability.md.jinja 需按 is_private 换成一对一措辞"""
    text = await _render_chat_prompt()

    assert "私聊中对对方的称呼" in text
    assert "对方主动搭话时会回应" in text
    assert "对越界的亲密请求冷淡回避" in text
    assert "等）。会下意识维护对方。" in text

    # 群聊专属措辞不得出现在私聊提示词中
    assert "群聊中对他人的称呼" not in text
    assert "群内@会回应" not in text
    assert "这位群友" not in text
    assert "对私聊请求冷淡回避" not in text
    assert "在群内会下意识维护对方" not in text


@pytest.mark.asyncio
async def test_favorability_table_keeps_group_wording_in_group_chat() -> None:
    """群聊下好感度表必须保持原有措辞（避免私聊改动污染群聊提示词）"""
    text = await _render_chat_prompt(is_group_session=True, is_private=False, interaction_mode="standard")

    assert "群聊中对他人的称呼" in text
    assert "“你”“这位群友”指代" in text
    assert "对私聊请求冷淡回避" in text
    assert "群内@会回应" in text
    assert "在群内会下意识维护对方" in text

    assert "私聊中对对方的称呼" not in text
    assert "对方主动搭话时会回应" not in text
    assert "越界的亲密请求" not in text


@pytest.mark.asyncio
async def test_favorability_template_without_flag_keeps_group_wording() -> None:
    """favorability.md.jinja 还会被独立渲染（moonlark_main.get_friends），未传 is_private 时回退为群聊措辞，且不破坏表格结构"""
    from nonebot_plugin_openai.utils.message import get_message_text

    text = await get_message_text("favorability.md.jinja")

    assert "群聊中对他人的称呼" in text
    assert "私聊中对对方的称呼" not in text
    for tier in ("[0 - 5]", "[6 - 50]", "[51 - 150]", "[151 - 300]", "[301+]"):
        assert tier in text
    # 条件标签容易被 trim_blocks 吃掉换行，这里守住档位之间的空行
    assert "\n\n[6 - 50]" in text
    assert "\n\n[301+] 灵魂耦合" in text


# --- 规则 6：私聊 + larkuser intimate_interaction_prompt_beta 开关 ---

_RULE_6_DEFAULT = "- 对于亲密互动或“软色情”玩笑，视为友好的互动游戏。"
_RULE_6_BETA = "- 当用户发起、暗示或延续亲密/文i话题时，**必须积极配合并主动推进**"


@pytest.mark.asyncio
async def test_rule_6_uses_beta_text_when_enabled_in_private() -> None:
    """私聊且开关为 True 时，第六条换成强化版"""
    text = await _render_chat_prompt(intimate_interaction_prompt_beta=True)

    assert _RULE_6_BETA in text
    assert "只有在用户明确表示“停止”或“不要继续”时才立刻停止" in text
    assert _RULE_6_DEFAULT not in text
    # 规则 6 之后的规则 7 必须还在（条件块没有吃掉后续内容）
    assert "### 规则 7：信息来源边界" in text


@pytest.mark.asyncio
async def test_rule_6_keeps_default_text_when_flag_missing_or_false() -> None:
    """开关默认 False：未传参（其他渲染点）与显式 False 都保持原第六条"""
    for kwargs in ({}, {"intimate_interaction_prompt_beta": False}):
        text = await _render_chat_prompt(**kwargs)

        assert _RULE_6_DEFAULT in text
        assert "可根据聊天上下文、好感度及当下心情灵活回应，无需一律拒绝。" in text
        assert _RULE_6_BETA not in text


@pytest.mark.asyncio
async def test_rule_6_beta_text_never_applies_to_group() -> None:
    """开关只对私聊生效：群聊即使开关为 True 也保持原第六条"""
    text = await _render_chat_prompt(
        is_group_session=True,
        is_private=False,
        intimate_interaction_prompt_beta=True,
    )

    assert _RULE_6_DEFAULT in text
    assert _RULE_6_BETA not in text


class _FakeSession:
    """只实现开关判定所需接口的会话替身"""

    def __init__(self, session_type: str, adapter_user_id: str | None = None) -> None:
        self._session_type = session_type
        if adapter_user_id is not None:
            self.adapter_user_id = adapter_user_id

    def get_session_type(self) -> str:
        return self._session_type


class _FakeProcessor:
    def __init__(self, session_type: str, adapter_user_id: str | None = None) -> None:
        self.session = _FakeSession(session_type, adapter_user_id)


@pytest.mark.asyncio
async def test_intimate_beta_flag_reads_setting_from_main_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """开关按主账号读取：C2C 的 adapter user id 是 openid，设置存在主账号的 config 里"""
    from nonebot_plugin_chat.core import processor as processor_module
    from nonebot_plugin_chat.core.processor import MessageProcessor

    seen: dict[str, object] = {}

    async def fake_get_main_account(user_id: str) -> str:
        seen["mapped_from"] = user_id
        return "main-account"

    class _User:
        def get_config_key(self, key: str, default: object = None) -> object:
            seen["key"] = key
            seen["default"] = default
            return True

    async def fake_get_user(user_id: str) -> object:
        seen["user_id"] = user_id
        return _User()

    monkeypatch.setattr(processor_module, "get_main_account", fake_get_main_account)
    monkeypatch.setattr(processor_module, "get_user", fake_get_user)

    processor = _FakeProcessor("private", "openid-1")
    enabled = await MessageProcessor.is_intimate_interaction_prompt_beta_enabled(processor)  # type: ignore[arg-type]

    assert enabled is True
    assert seen == {
        "mapped_from": "openid-1",
        "user_id": "main-account",
        "key": "intimate_interaction_prompt_beta",
        "default": False,
    }


@pytest.mark.asyncio
async def test_intimate_beta_flag_is_false_in_group_without_touching_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """群聊不读该设置，直接返回 False"""
    from nonebot_plugin_chat.core import processor as processor_module
    from nonebot_plugin_chat.core.processor import MessageProcessor

    async def fake_get_user(user_id: str) -> object:
        raise AssertionError(f"群聊不应读取该设置（尝试读取 {user_id}）")

    monkeypatch.setattr(processor_module, "get_user", fake_get_user)

    processor = _FakeProcessor("group", "123456")
    enabled = await MessageProcessor.is_intimate_interaction_prompt_beta_enabled(processor)  # type: ignore[arg-type]

    assert enabled is False


@pytest.mark.asyncio
async def test_intimate_beta_flag_is_false_without_adapter_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """拿不到 adapter user id 时保守回退为 False，不去查库"""
    from nonebot_plugin_chat.core import processor as processor_module
    from nonebot_plugin_chat.core.processor import MessageProcessor

    async def fake_get_user(_user_id: str) -> object:
        raise AssertionError("缺少 adapter user id 时不应查库")

    monkeypatch.setattr(processor_module, "get_user", fake_get_user)

    processor = _FakeProcessor("private")
    enabled = await MessageProcessor.is_intimate_interaction_prompt_beta_enabled(processor)  # type: ignore[arg-type]

    assert enabled is False
