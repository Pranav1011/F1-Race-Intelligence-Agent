"""
Chat router - Handles conversation endpoints.
"""

import logging
import os
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from agent import F1Agent, get_agent

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize agent on first request
_agent: F1Agent | None = None


def get_chat_agent() -> F1Agent:
    """Get or create the chat agent."""
    global _agent
    if _agent is None:
        _agent = get_agent(
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            groq_api_key=os.getenv("GROQ_API_KEY"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
        )
    return _agent


class ChatMessage(BaseModel):
    """Chat message from user."""

    content: str
    session_id: str | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    """Chat response from agent."""

    content: str
    session_id: str
    query_type: str = "unknown"
    response_type: str = "text"
    confidence: float = 0.0
    error: str | None = None
    visualizations: list[dict] = []


@router.post("/", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Send a message and get a response.

    This is the HTTP endpoint for non-streaming responses.
    For streaming, use the WebSocket endpoint.
    """
    try:
        agent = get_chat_agent()

        # Generate session ID if not provided
        session_id = message.session_id or str(uuid.uuid4())

        # Process message through agent
        result = await agent.chat(
            message=message.content,
            session_id=session_id,
            user_id=message.user_id,
        )

        # Build visualization list from visualization spec
        viz_spec = result.get("visualization")
        visualizations = [viz_spec] if viz_spec else []

        return ChatResponse(
            content=result.get("message", ""),
            session_id=session_id,
            query_type=str(result.get("query_type", "unknown")),
            response_type=str(result.get("response_type", "text")),
            confidence=result.get("confidence", 0.0),
            error=result.get("error"),
            visualizations=visualizations,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    agent = get_chat_agent()

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            if data.get("type") != "message":
                continue

            content = data.get("content", "")
            session_id = data.get("session_id") or str(uuid.uuid4())
            user_id = data.get("user_id")

            # Send session ID back
            await websocket.send_json({
                "type": "session",
                "session_id": session_id,
            })

            try:
                # Process message (non-streaming for now)
                # TODO: Implement true streaming with LangGraph callbacks
                result = await agent.chat(
                    message=content,
                    session_id=session_id,
                    user_id=user_id,
                )

                # Send query type info
                await websocket.send_json({
                    "type": "metadata",
                    "query_type": str(result.get("query_type", "unknown")),
                    "response_type": str(result.get("response_type", "text")),
                    "confidence": result.get("confidence", 0.0),
                })

                # Send response as tokens (simulated streaming)
                response_content = result.get("message", "")

                # Send in chunks for a streaming feel
                chunk_size = 50
                for i in range(0, len(response_content), chunk_size):
                    chunk = response_content[i:i + chunk_size]
                    await websocket.send_json({
                        "type": "token",
                        "token": chunk,
                    })

                # Send completion
                await websocket.send_json({
                    "type": "done",
                    "error": result.get("error"),
                })

            except Exception as e:
                logger.error(f"WebSocket chat error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": str(e),
                })
                await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """Get conversation history for a session."""
    agent = get_chat_agent()
    history = agent.get_session_history(session_id)
    return {"session_id": session_id, "messages": history}


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear a session's history."""
    agent = get_chat_agent()
    agent.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}
