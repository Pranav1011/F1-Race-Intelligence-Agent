"""
Sessions router - Manages conversation sessions.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/")
async def list_sessions(
    user_id: str | None = None,
    limit: int = 20,
):
    """
    List conversation sessions for a user.
    """
    # TODO: Query from Redis/PostgreSQL
    return {
        "sessions": [],
        "total": 0,
        "message": "Session management not yet implemented.",
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """
    Get a specific session with its conversation history.
    """
    # TODO: Query from Redis/PostgreSQL
    raise HTTPException(
        status_code=404,
        detail=f"Session {session_id} not found. Session management not yet implemented.",
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session and its history.
    """
    # TODO: Delete from Redis/PostgreSQL
    raise HTTPException(
        status_code=404,
        detail=f"Session {session_id} not found. Session management not yet implemented.",
    )
