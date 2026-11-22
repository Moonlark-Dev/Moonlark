"""会话级 Chat 屏蔽：供其他插件（例如海龟汤）临时让 Moonlark 停止回话。

屏蔽只作用于「是否生成回复」这一层：消息仍会照常进入会话上下文与数据库，
游戏结束后 Moonlark 依然记得期间发生了什么；但普通消息、事件、定时器、
冷群自动接话与主动私聊都不会触发回复。

按 ``session_id``（``nonebot_plugin_larkutils.get_group_id()`` 的返回值）登记，
并允许同一会话被多个调用方同时屏蔽（``owner`` 去重计数），
这样两个插件互相不会把对方的屏蔽解开。
"""

from __future__ import annotations

# session_id -> {owner: reason}
_suspenders: dict[str, dict[str, str]] = {}


# 海龟汤等插件使用的 owner 常量由调用方自带，这里只做登记
def suspend_chat(session_id: str, owner: str, reason: str = "") -> None:
    """暂停指定会话的 Chat 回复（可重入：同一个 owner 重复调用只记一次）。"""
    _suspenders.setdefault(session_id, {})[owner] = reason


def resume_chat(session_id: str, owner: str) -> None:
    """撤销指定 owner 对会话的屏蔽；没有其他 owner 时恢复回复。"""
    owners = _suspenders.get(session_id)
    if not owners:
        return
    owners.pop(owner, None)
    if not owners:
        _suspenders.pop(session_id, None)


def is_chat_suspended(session_id: str) -> bool:
    """该会话当前是否被屏蔽。"""
    return bool(_suspenders.get(session_id))


def suspended_sessions() -> dict[str, dict[str, str]]:
    """返回当前屏蔽状态的快照（只读，供测试与诊断使用）。"""
    return {session_id: dict(owners) for session_id, owners in _suspenders.items()}
