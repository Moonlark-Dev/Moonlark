"""SessionQueue 行为测试：迭代、长度、布尔与弹出"""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.session.base import SessionQueue


@pytest.fixture
def queue() -> "SessionQueue":
    from nonebot_plugin_chat.core.session.base import SessionQueue

    notifications: list[int] = []

    def on_item_queued() -> None:
        notifications.append(1)

    return SessionQueue(on_item_queued)


def test_queue_is_iterable(queue: "SessionQueue") -> None:
    """队列应支持直接迭代（chat_monitor 依赖该行为）"""
    queue.append(("message", ("m1",)))
    queue.append(("event", ("prompt", "probability")))
    assert [item[0] for item in queue] == ["message", "event"]


def test_queue_len_and_bool(queue: "SessionQueue") -> None:
    assert len(queue) == 0
    assert not queue
    queue.append(("message", ("m1",)))
    assert len(queue) == 1
    assert queue


def test_queue_pop_and_notify(queue: "SessionQueue") -> None:
    queue.append(("message", ("m1",)))
    item = queue.pop(0)
    assert item == ("message", ("m1",))
    assert len(queue) == 0


def test_queue_iteration_does_not_consume(queue: "SessionQueue") -> None:
    """迭代不应弹出元素（只读遍历）"""
    queue.append(("event", ("prompt", "none")))
    list(queue)
    assert len(queue) == 1
