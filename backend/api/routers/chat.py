"""
Chat router - Handles conversation endpoints.
"""

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel

from agent import F1Agent, get_agent
from preprocessing import QueryPreprocessor, PreprocessedQuery, QueryHistoryManager, get_history_manager
from api.streaming import StreamingContext, StreamStage, get_status_message

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize agent on first request
_agent: F1Agent | None = None
_preprocessor: QueryPreprocessor | None = None
_history_manager: QueryHistoryManager | None = None


def get_chat_agent() -> F1Agent:
    """Get or create the chat agent."""
    global _agent
    if _agent is None:
        _agent = get_agent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            groq_api_key=os.getenv("GROQ_API_KEY"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
        )
    return _agent


def get_query_preprocessor() -> QueryPreprocessor:
    """Get or create the query preprocessor."""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = QueryPreprocessor()
    return _preprocessor


async def get_query_history_manager() -> QueryHistoryManager:
    """Get or create the query history manager."""
    global _history_manager
    if _history_manager is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
        _history_manager = await get_history_manager(redis_url)
    return _history_manager


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
        preprocessor = get_query_preprocessor()

        # Generate session ID if not provided
        session_id = message.session_id or str(uuid.uuid4())

        # Preprocess the query
        preprocessed = preprocessor.process(message.content)

        # Track query in history
        try:
            history_manager = await get_query_history_manager()
            await history_manager.add_query(
                user_id=message.user_id,
                session_id=session_id,
                query=message.content,
                preprocessed=preprocessed.to_dict(),
            )
        except Exception as e:
            logger.warning(f"Failed to track query history: {e}")

        # Process message through agent with preprocessing hints
        result = await agent.chat(
            message=message.content,
            session_id=session_id,
            user_id=message.user_id,
            preprocessed=preprocessed.to_dict(),
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
    - Client sends: {"type": "message", "content": "...", "session_id": "...", "user_id": "..."}

    Server events:
    - session: Session ID confirmation
    - interpreted: Preprocessed query info (original, expanded, corrections, intent)
    - status: Processing stage updates (stage, message, progress)
    - tool_start: Tool execution started
    - tool_progress: Tool execution progress
    - tool_end: Tool execution completed
    - metadata: Query metadata (type, response_type, confidence)
    - visualization: Chart specification
    - token: Streaming response token
    - done: Processing complete
    - error: Error occurred
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

            # Create streaming context for this message
            ctx = StreamingContext(websocket.send_json)

            # Send session ID back
            await websocket.send_json({
                "type": "session",
                "session_id": session_id,
            })

            try:
                # Step 1: Preprocess the query
                await ctx.status(StreamStage.PREPROCESSING)
                preprocessor = get_query_preprocessor()
                preprocessed = preprocessor.process(content)

                # Send interpreted query info
                await ctx.interpreted(
                    original=preprocessed.original,
                    expanded=preprocessed.expanded_display,
                    corrections=preprocessed.corrections,
                    intent=preprocessed.intent,
                    confidence=preprocessed.intent_confidence,
                )

                # Track query in history (non-blocking)
                try:
                    history_manager = await get_query_history_manager()
                    await history_manager.add_query(
                        user_id=user_id,
                        session_id=session_id,
                        query=content,
                        preprocessed=preprocessed.to_dict(),
                    )
                except Exception as e:
                    logger.debug(f"Failed to track query history: {e}")

                # Send context-aware status message
                if preprocessed.is_comparison and len(preprocessed.drivers) >= 2:
                    detail = f"Comparing {' vs '.join(preprocessed.drivers[:2])}"
                elif preprocessed.drivers:
                    detail = f"Analyzing {', '.join(preprocessed.drivers)}"
                elif preprocessed.circuits:
                    detail = f"Looking at {', '.join(preprocessed.circuits)}"
                else:
                    detail = None

                await ctx.status(StreamStage.UNDERSTANDING, detail=detail)

                # Process message with status callbacks
                async def status_callback(stage: str, message: str):
                    try:
                        stage_enum = StreamStage(stage)
                    except ValueError:
                        stage_enum = StreamStage.PROCESSING
                    await ctx.status(stage_enum, message)

                # Pass preprocessed hints to agent
                result = await agent.chat(
                    message=content,
                    session_id=session_id,
                    user_id=user_id,
                    status_callback=status_callback,
                    preprocessed=preprocessed.to_dict(),
                )

                # Send query metadata
                await ctx.metadata(
                    query_type=str(result.get("query_type", "unknown")),
                    response_type=str(result.get("response_type", "text")),
                    confidence=result.get("confidence", 0.0),
                )

                # Send visualization if available
                viz_spec = result.get("visualization")
                if viz_spec:
                    await ctx.visualization(viz_spec)

                # Stream the response in chunks
                await ctx.status(StreamStage.GENERATING)
                response_content = result.get("message", "")

                # Send in chunks for a streaming feel (word-aware chunking)
                words = response_content.split(" ")
                chunk = ""
                for word in words:
                    chunk += word + " "
                    if len(chunk) >= 40:
                        await ctx.token(chunk)
                        chunk = ""
                if chunk:
                    await ctx.token(chunk)

                # Send completion
                await ctx.complete(error=result.get("error"))

            except Exception as e:
                logger.error(f"WebSocket chat error: {e}")
                await ctx.error(str(e))
                await ctx.complete(error=str(e))

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


class SuggestionResponse(BaseModel):
    """Query suggestion response."""
    text: str
    type: str
    confidence: float = 1.0


@router.get("/suggestions")
async def get_suggestions(
    session_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    current_query: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=10),
) -> list[SuggestionResponse]:
    """
    Get smart query suggestions.

    Returns suggestions based on:
    - Recent queries (personalized)
    - Popular queries (global trends)
    - Related queries (by entity)
    - Follow-up suggestions (by intent pattern)

    Args:
        session_id: Current session ID
        user_id: User ID for personalized suggestions
        current_query: Current query for follow-up suggestions
        limit: Max suggestions to return (1-10)

    Returns:
        List of query suggestions
    """
    try:
        history_manager = await get_query_history_manager()

        # Preprocess current query for context
        preprocessed = None
        if current_query:
            preprocessor = get_query_preprocessor()
            preprocessed = preprocessor.process(current_query).to_dict()

        suggestions = await history_manager.get_suggestions(
            user_id=user_id,
            session_id=session_id,
            current_query=current_query,
            preprocessed=preprocessed,
            limit=limit,
        )

        return [
            SuggestionResponse(
                text=s.text,
                type=s.type,
                confidence=s.confidence,
            )
            for s in suggestions
        ]

    except Exception as e:
        logger.error(f"Failed to get suggestions: {e}")
        # Return default suggestions on error
        return [
            SuggestionResponse(text="Who is leading the championship?", type="default"),
            SuggestionResponse(text="Compare Verstappen vs Norris", type="default"),
            SuggestionResponse(text="Show me the last race results", type="default"),
        ]


@router.get("/trending")
async def get_trending_queries(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(5, ge=1, le=20),
) -> list[str]:
    """
    Get trending queries in recent hours.

    Args:
        hours: Time window in hours (1-168)
        limit: Max queries to return (1-20)

    Returns:
        List of trending query strings
    """
    try:
        history_manager = await get_query_history_manager()
        return await history_manager.get_trending(hours=hours, limit=limit)
    except Exception as e:
        logger.error(f"Failed to get trending queries: {e}")
        return []
