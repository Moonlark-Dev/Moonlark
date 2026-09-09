from unittest.mock import MagicMock


def test_get_qq_user_id_returns_user_id_for_group_chat() -> None:
    """QQ 官方机器人群聊事件应返回用户 ID，用于 markdown 卡片内 @ 用户"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
    from nonebot_plugin_quick_math.commands.main import get_qq_user_id

    event = MagicMock(spec=GroupAtMessageCreateEvent)
    event.get_user_id.return_value = "member_openid_123"

    assert get_qq_user_id(MagicMock(spec=QQBot), event) == "member_openid_123"


def test_get_qq_user_id_returns_none_for_c2c_chat() -> None:
    """C2C 单聊事件不支持 qqbot-at-user 提及（发送会报 ActionFailed），应返回 None 跳过 @ 前缀"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.adapters.qq.event import C2CMessageCreateEvent
    from nonebot_plugin_quick_math.commands.main import get_qq_user_id

    event = MagicMock(spec=C2CMessageCreateEvent)
    event.get_user_id.return_value = "user_openid_123"

    assert get_qq_user_id(MagicMock(spec=QQBot), event) is None


def test_get_qq_user_id_returns_none_for_other_adapters() -> None:
    """非 QQ 官方机器人（如 OneBot V11）不应生成用户 ID"""
    from nonebot_plugin_quick_math.commands.main import get_qq_user_id

    assert get_qq_user_id(MagicMock(), MagicMock()) is None
