#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""WebSocket 广播循环——增量推送，每 30 秒全量快照一次。"""

import asyncio
import copy
from typing import Any

from nonebot import get_driver
from nonebot.log import logger

from .ws_manager import ws_manager

_cycle_count: int = 0
_full_snapshot_interval: int = 15  # 每 15 个增量周期（~30 秒）送一次全量

# 上一个状态快照，用于计算增量
_prev_state: dict[str, Any] = {}


async def collect_full_status() -> dict[str, Any]:
    """收集前端需要的全量状态数据。"""
    from .routers.sessions import build_status

    return await build_status()


def _normalize_session(s: dict[str, Any]) -> dict[str, Any]:
    """标准化会话数据，用于 diff 比较。"""
    return {
        "id": s["id"],
        "type": s.get("type", "unknown"),
        "name": s.get("name", s["id"]),
        "state": s.get("state", "idle"),
        "last_activity": s.get("last_activity"),
        "message_count": s.get("message_count", 0),
    }


def _diff_status(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """比较两个状态，生成增量数据包。

    只有在内容变化时才在增量包中包含对应字段。
    """
    inc: dict[str, Any] = {"type": "incremental_update", "server_time": current.get("server_time", "")}

    # ---- Mood（体积小，每次都送） ----
    inc["mood"] = current.get("mood", {})

    # ---- Sessions ----
    cur_sessions_raw: list[dict] = current.get("sessions", [])
    prev_sessions_raw: list[dict] = previous.get("sessions", [])
    cur_session_map: dict[str, dict] = {}
    for s in cur_sessions_raw:
        norm = _normalize_session(s)
        cur_session_map[norm["id"]] = norm

    prev_session_map: dict[str, dict] = {}
    for s in prev_sessions_raw:
        norm = _normalize_session(s)
        prev_session_map[norm["id"]] = norm

    # 新增或变化的 session
    updated: list[dict[str, Any]] = []
    removed: list[str] = []
    for sid, cur in cur_session_map.items():
        prev = prev_session_map.get(sid)
        if prev and prev == cur:
            continue  # 无变化
        updated.append(cur_session_raw(current, sid) if prev else cur_session_raw(current, sid))

    # 被移除的 session
    for sid in prev_session_map:
        if sid not in cur_session_map:
            removed.append(sid)

    if updated:
        inc["sessions_updated"] = updated
    if removed:
        inc["sessions_removed"] = removed

    # ---- EGO 决策历史增量 ----
    cur_ego = current.get("ego", {})
    prev_ego = previous.get("ego", {})
    cur_decisions: list = cur_ego.get("decision_history", [])
    prev_decisions: list = prev_ego.get("decision_history", [])

    if len(cur_decisions) > len(prev_decisions):
        inc["new_ego_decisions"] = cur_decisions[len(prev_decisions):]
    elif cur_decisions != prev_decisions and len(cur_decisions) > 0:
        # 决策列表被修改了（不是追加），把当前全都送
        inc["ego_decision_full"] = cur_decisions

    # ---- EGO 睡眠/活动状态变化 ----
    for field in ("sleep_mode", "tiredness", "current_activity", "mood_retention"):
        cv = cur_ego.get(field)
        pv = prev_ego.get(field)
        if cv != pv:
            inc.setdefault("ego_updates", {})[field] = cv

    # ---- ws_connections（直接更新，小字段） ----
    cw = current.get("ws_connections")
    pw = previous.get("ws_connections")
    if cw is not None and cw != pw:
        inc["ws_connections"] = cw

    # ---- 如果没有任何变化，送心跳 ----
    if not any(k.startswith(("sessions_", "new_", "ego_", "ws_")) for k in inc):
        inc["type"] = "heartbeat"
        inc.pop("mood", None)
        return inc

    return inc


def cur_session_raw(full: dict[str, Any], sid: str) -> dict[str, Any]:
    """从全量状态中找到指定 session 的原始数据。"""
    for s in full.get("sessions", []):
        if s.get("id") == sid:
            return _normalize_session(s)
    return {"id": sid}


async def _ws_broadcast_loop():
    """广播循环：增量推送为主，每 30 秒一次全量快照。"""
    global _cycle_count

    await asyncio.sleep(3)  # 等待 NoneBot 完全初始化
    while True:
        try:
            if ws_manager._connections:
                payload = await collect_full_status()

                global _prev_state
                if not _prev_state:
                    # 首次发送全量
                    payload["type"] = "status_snapshot"
                    await ws_manager.broadcast(payload)
                    _prev_state = copy.deepcopy(payload)
                elif _cycle_count >= _full_snapshot_interval:
                    # 定时全量快照
                    payload["type"] = "status_snapshot"
                    await ws_manager.broadcast(payload)
                    _prev_state = copy.deepcopy(payload)
                    _cycle_count = 0
                else:
                    # 增量推送
                    inc = _diff_status(payload, _prev_state)
                    await ws_manager.broadcast(inc)
                    # 无论如何更新缓存的上一状态（只保留 diff 需要的字段）
                    _prev_state["sessions"] = payload.get("sessions", [])
                    _prev_state["ego"] = payload.get("ego", {})
                    _prev_state["mood"] = payload.get("mood", {})
                    _prev_state["ws_connections"] = payload.get("ws_connections", 0)
                    _cycle_count += 1
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[ChatMonitor] 广播异常: {e}", exc_info=True)
        await asyncio.sleep(2)


@get_driver().on_startup
async def _start_ws_broadcast():
    """在 NoneBot 启动后启动 WebSocket 广播循环。"""
    asyncio.create_task(_ws_broadcast_loop())
