"""
Agent State Definition

Defines the state that flows through the LangGraph agent.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class QueryType(str, Enum):
    """Types of queries the agent can handle."""

    HISTORICAL_ANALYSIS = "historical_analysis"  # Past race analysis
    WHAT_IF_SIMULATION = "what_if_simulation"  # Hypothetical scenarios
    LIVE_INSIGHTS = "live_insights"  # Recent/current race insights
    GENERAL_KNOWLEDGE = "general_knowledge"  # F1 rules, history, etc.
    COMPARISON = "comparison"  # Driver/team comparisons
    UNKNOWN = "unknown"


class ResponseType(str, Enum):
    """Types of responses the agent can generate."""

    TEXT = "text"  # Plain text response
    CHART = "chart"  # Visualization needed
    TABLE = "table"  # Tabular data
    MIXED = "mixed"  # Combination of above


@dataclass
class QueryContext:
    """Extracted context from user query."""

    drivers: list[str] = field(default_factory=list)
    teams: list[str] = field(default_factory=list)
    races: list[str] = field(default_factory=list)
    seasons: list[int] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)  # lap_time, tire_deg, etc.
    time_range: str | None = None


@dataclass
class RetrievedData:
    """Data retrieved from various sources."""

    timescale_data: list[dict] = field(default_factory=list)
    neo4j_data: list[dict] = field(default_factory=list)
    vector_data: list[dict] = field(default_factory=list)
    source_metadata: dict = field(default_factory=dict)


class AgentState:
    """
    State that flows through the LangGraph agent.

    Uses TypedDict pattern for LangGraph compatibility.
    """

    pass


# LangGraph requires TypedDict for state
from typing import TypedDict


class AgentStateDict(TypedDict):
    """State dictionary for LangGraph."""

    # Conversation history (uses add_messages reducer for appending)
    messages: Annotated[list[BaseMessage], add_messages]

    # Query understanding
    query_type: QueryType
    query_context: dict  # Serialized QueryContext
    confidence: float

    # Retrieved data
    retrieved_data: dict  # Serialized RetrievedData

    # Response generation
    response_type: ResponseType
    analysis_result: str
    visualization_spec: dict | None  # Chart specification if needed

    # Metadata
    session_id: str
    user_id: str | None
    iteration_count: int
    error: str | None


def create_initial_state(
    session_id: str,
    user_id: str | None = None,
) -> AgentStateDict:
    """Create initial agent state."""
    return AgentStateDict(
        messages=[],
        query_type=QueryType.UNKNOWN,
        query_context={},
        confidence=0.0,
        retrieved_data={},
        response_type=ResponseType.TEXT,
        analysis_result="",
        visualization_spec=None,
        session_id=session_id,
        user_id=user_id,
        iteration_count=0,
        error=None,
    )
