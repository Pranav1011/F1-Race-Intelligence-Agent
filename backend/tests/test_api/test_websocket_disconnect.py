"""
A client that leaves mid-answer stops the agent and leaves one info log line,
not an ASGI traceback from sending on a closed socket.
"""

import asyncio
import logging

import pytest

from api.routers import chat
from api.streaming import ClientDisconnectedError, StreamingContext, StreamStage

CLOSED = RuntimeError('Cannot call "send" once a close message has been sent.')


class FakeWebSocket:
    """Accepts one message, then the client disconnects while the agent works."""

    def __init__(self, fail_sends_after_disconnect: bool = True):
        self.sent: list[dict] = []
        self.disconnected = asyncio.Event()
        self.fail_sends = fail_sends_after_disconnect
        self._messages = [{"type": "message", "content": "Monza 2024?", "session_id": "s1"}]

    async def accept(self):
        pass

    async def receive_json(self):
        if self._messages:
            return self._messages.pop(0)
        await asyncio.Event().wait()

    async def receive(self):
        await self.disconnected.wait()
        return {"type": "websocket.disconnect", "code": 1001}

    async def send_json(self, payload: dict):
        if self.disconnected.is_set() and self.fail_sends:
            raise CLOSED
        self.sent.append(payload)


class SlowAgent:
    def __init__(self, websocket: FakeWebSocket):
        self.websocket = websocket
        self.cancelled = False

    async def chat(self, **kwargs):
        self.websocket.disconnected.set()  # the user closes the tab mid-answer
        try:
            await asyncio.sleep(30)  # a slow LLM call
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return {"message": "never sent"}


async def test_disconnect_mid_answer_cancels_the_agent_without_a_traceback(monkeypatch, caplog):
    websocket = FakeWebSocket()
    agent = SlowAgent(websocket)
    monkeypatch.setattr(chat, "get_chat_agent", lambda: agent)

    async def no_history():
        raise RuntimeError("history store unavailable")

    monkeypatch.setattr(chat, "get_query_history_manager", no_history)

    with caplog.at_level(logging.INFO, logger="api.routers.chat"):
        await asyncio.wait_for(chat.websocket_chat(websocket), timeout=5)

    assert agent.cancelled
    assert not any(m.get("type") in ("done", "error") for m in websocket.sent)
    messages = [r.getMessage() for r in caplog.records if r.name == "api.routers.chat"]
    assert "WebSocket client disconnected; stopped any answer in progress" in messages
    assert not any(r.levelno >= logging.ERROR for r in caplog.records if r.name == "api.routers.chat")


async def test_send_on_a_closed_socket_raises_client_disconnected_once():
    calls = 0

    async def send(payload):
        nonlocal calls
        calls += 1
        raise CLOSED

    ctx = StreamingContext(send)

    with pytest.raises(ClientDisconnectedError):
        await ctx.status(StreamStage.PROCESSING)
    with pytest.raises(ClientDisconnectedError):
        await ctx.complete()

    assert ctx.closed
    assert calls == 1


async def test_other_send_errors_still_raise():
    async def send(payload):
        raise ValueError("payload is not JSON serializable")

    with pytest.raises(ValueError):
        await StreamingContext(send).token("hi")
