from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()

    async def connect(self, ws: WebSocket) -> asyncio.Queue:
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        self._queues.add(q)
        return q

    def disconnect(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    async def broadcast(self, message: dict) -> None:
        for q in self._queues:
            await q.put(message)


manager = ConnectionManager()


@router.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket) -> None:
    q = await manager.connect(ws)
    try:
        while True:
            alert = await q.get()
            await ws.send_json(alert)
    except WebSocketDisconnect:
        manager.disconnect(q)
    except Exception:
        manager.disconnect(q)
