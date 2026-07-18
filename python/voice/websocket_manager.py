"""
Voice WebSocket Connection Manager — Instant State Broadcast.

Provides a singleton ``VoiceWSManager`` that tracks all active ``/ws/status``
clients and enables instant push of ``state_change``, ``caption_user``, and
``caption_barq`` events without waiting for the 100ms poll cycle.

Usage:
    manager = VoiceWSManager.get_instance()
    await manager.register(websocket)
    await manager.unregister(websocket)
    await manager.broadcast({"type": "state_change", "status": "listening"})
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from .evolution_logger import get_evolution_logger

logger = logging.getLogger("barq.voice.ws")


class VoiceWSManager:
    """Thread-safe singleton WebSocket connection manager for voice state broadcasts."""

    _instance: VoiceWSManager | None = None
    _lock = asyncio.Lock()

    def __new__(cls) -> VoiceWSManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._clients: set[WebSocket] = set()
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> VoiceWSManager:
        if cls._instance is None:
            cls()
        assert cls._instance is not None
        return cls._instance

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def register(self, ws: WebSocket) -> None:
        """Register a newly-accepted WebSocket client for broadcasts."""
        async with self._lock:
            self._clients.add(ws)
        logger.debug("[VoiceWS] Client registered (%d total)", len(self._clients))

    async def unregister(self, ws: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""
        async with self._lock:
            self._clients.discard(ws)
        logger.debug("[VoiceWS] Client unregistered (%d remaining)", len(self._clients))

    @staticmethod
    def _ws_is_connected(ws: WebSocket) -> bool:
        """Check if a WebSocket is still in a connected state.

        FastAPI's WebSocket has ``client_state`` (CONNECTED or DISCONNECTED)
        and ``application_state`` attributes.  We check both to avoid sending
        on a socket that has been closed on either end.
        """
        try:
            from starlette.websockets import WebSocketState
            # client_state: CONNECTED = 1, DISCONNECTED = 2, CONNECTING = 0
            if hasattr(ws, "client_state") and ws.client_state != WebSocketState.CONNECTED:
                return False
            if hasattr(ws, "application_state") and ws.application_state != WebSocketState.CONNECTED:
                return False
            return True
        except Exception:
            # If we can't determine the state, optimistically try to send
            return True

    async def broadcast(self, msg: dict[str, Any]) -> None:
        """Fire-and-forget broadcast to all connected clients.

        Failed sends are silently dropped — the client will reconnect
        and re-register naturally via the WS endpoint's accept loop.
        """
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._clients:
                # Check WebSocket state before sending
                if not self._ws_is_connected(ws):
                    dead.append(ws)
                    continue
                try:
                    await ws.send_json(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)
            if dead:
                logger.debug("[VoiceWS] Pruned %d dead client(s)", len(dead))
                # Log WS disconnect events to evolution tracker
                evo = get_evolution_logger()
                for _ in dead:
                    evo.record("ws_disconnect", metadata={"client_type": "voice_status"})

    async def broadcast_state(self, status: str) -> None:
        """Convenience: broadcast a ``state_change`` event with the given status.

        Status values: ``idle``, ``listening``, ``processing``, ``speaking``.
        """
        await self.broadcast({
            "type": "state_change",
            "status": status,
        })

    async def send_safe(self, ws: WebSocket, msg: dict[str, Any]) -> bool:
        """Send a JSON message to a specific WebSocket with state verification.

        Verifies the connection state before sending and logs failures to
        the evolution tracker.  Returns True if the send succeeded.

        Args:
            ws: The WebSocket to send to.
            msg: The JSON-serializable dict to send.

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        if not self._ws_is_connected(ws):
            logger.debug("[VoiceWS] Skipping send to disconnected socket")
            return False
        try:
            await ws.send_json(msg)
            return True
        except Exception as e:
            logger.debug("[VoiceWS] Send failed: %s", e)
            # Remove from active clients
            async with self._lock:
                self._clients.discard(ws)
            # Log to evolution tracker
            evo = get_evolution_logger()
            evo.record("ws_disconnect", metadata={
                "client_type": "voice_status",
                "error": str(e)[:80],
            })
            return False
