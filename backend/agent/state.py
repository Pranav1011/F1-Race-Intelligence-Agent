"""
Agent State Definition

Defines the state that flows through the LangGraph agent.
Enhanced with support for CRAG pattern, parallel execution, and structured analysis.
"""

from typing import Annotated, TypedDict, Any

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class EnhancedAgentState(TypedDict):
    """
    Enhanced state dictionary for the F1 Race Intelligence Agent.

    Supports the new architecture:
    UNDERSTAND → PLAN → EXECUTE → PROCESS → EVALUATE → GENERATE

    With CRAG (Corrective RAG) pattern for looping back to PLAN
    if data is insufficient.
    """

    # Conversation history (uses add_messages reducer for appending)
    messages: Annotated[list[BaseMessage], add_messages]

    # Preprocessing hints (from QueryPreprocessor)
    preprocessed_query: dict  # Intent, entities, corrections, hints

    # UNDERSTAND node output
    query_understanding: dict  # Serialized QueryUnderstanding schema

    # PLAN node output
    data_plan: dict  # Serialized DataPlan schema

    # EXECUTE node output
    raw_data: dict  # Tool results keyed by tool_id

    # PROCESS node output
    processed_analysis: dict  # Serialized ProcessedAnalysis schema

    # EVALUATE node output
    evaluation: dict  # Serialized EvaluationResult schema
    evaluation_feedback: str  # Feedback for PLAN node if looping

    # ENRICH node output (RAG context)
    enriched_context: dict  # Contains race_context, community_insights, regulations, similar_analyses

    # GENERATE node output
    analysis_result: str  # Final text response
    visualization_spec: dict | None  # Chart specification
    response_type: str  # "TEXT", "CHART", "MIXED"

    # VALIDATE node output
    validation_result: dict | None  # Contains passes_validation, score, issues, suggestions

    # Memory context
    user_context: str  # Retrieved from long-term memory (Mem0)
    session_context: dict  # Working context from Redis

    # Metadata
    session_id: str
    user_id: str | None
    iteration_count: int  # For CRAG loop limit
    error: str | None


def create_initial_state(
    session_id: str,
    user_id: str | None = None,
    user_context: str = "",
    session_context: dict | None = None,
) -> EnhancedAgentState:
    """Create initial agent state for a new session."""
    return EnhancedAgentState(
        messages=[],
        preprocessed_query={},
        query_understanding={},
        data_plan={},
        raw_data={},
        processed_analysis={},
        evaluation={},
        evaluation_feedback="",
        enriched_context={},
        analysis_result="",
        visualization_spec=None,
        response_type="TEXT",
        validation_result=None,
        user_context=user_context,
        session_context=session_context or {},
        session_id=session_id,
        user_id=user_id,
        iteration_count=0,
        error=None,
    )


# Keep old state for backwards compatibility
AgentStateDict = EnhancedAgentState
