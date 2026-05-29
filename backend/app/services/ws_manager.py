"""WebSocket 连接管理：按 task_id 维护订阅列表，跨线程广播。"""
from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """task_id -> 该任务的所有 WebSocket 连接。

    后台线程产生进度时通过 broadcast(task_id, payload) 推送；内部用 asyncio.run_coroutine_threadsafe
    把发送动作扔回主事件循环。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, task_id: str, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._connections[task_id].append(ws)

    def disconnect(self, task_id: str, ws: WebSocket) -> None:
        with self._lock:
            if ws in self._connections.get(task_id, []):
                self._connections[task_id].remove(ws)

    def broadcast(self, task_id: str, payload: dict[str, Any]) -> None:
        """跨线程安全广播。后台线程调用此函数即可。"""
        if not self._loop or self._loop.is_closed():
            return
        with self._lock:
            targets = list(self._connections.get(task_id, []))
        if not targets:
            return

        async def _send_all() -> None:
            dead: list[WebSocket] = []
            for ws in targets:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(task_id, ws)

        asyncio.run_coroutine_threadsafe(_send_all(), self._loop)


manager = ConnectionManager()
