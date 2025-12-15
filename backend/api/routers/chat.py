"""
Chat router - Handles conversation endpoints.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter()


class ChatMessage(BaseModel):
    """Chat message from user."""

    content: str
    session_id: str | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    """Chat response from agent."""

    content: str
    ui_mode: str = "chat"
    visualizations: list[dict] = []


@router.post("/", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Send a message and get a response.

    This is the HTTP endpoint for non-streaming responses.
    For streaming, use the WebSocket endpoint.
    """
    # TODO: Implement agent invocation
    return ChatResponse(
        content=f"Echo: {message.content}\n\n(Agent not yet implemented)",
        ui_mode="chat",
        visualizations=[],
    )


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat responses.

    Protocol:
    - Client sends: {"type": "message", "content": "...", "session_id": "..."}
    - Server sends: {"type": "token", "token": "..."} for streaming
    - Server sends: {"type": "tool_start", "tool": {...}} when tool starts
    - Server sends: {"type": "tool_end", "tool_id": "..."} when tool ends
    - Server sends: {"type": "ui_mode", "mode": "..."} for UI changes
    - Server sends: {"type": "visualization", "spec": {...}} for charts
    - Server sends: {"type": "done"} when complete
    """
    await websocket.accept()

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            if data.get("type") != "message":
                continue

            content = data.get("content", "")

            # TODO: Implement actual agent streaming
            # For now, just echo back
            await websocket.send_json({
                "type": "token",
                "token": f"Echo: {content}\n\n(Agent streaming not yet implemented)",
            })

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
