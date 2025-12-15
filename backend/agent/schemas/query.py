"""Schemas for query understanding and data planning."""

from enum import Enum
from pydantic import BaseModel, Field


class AnalysisScope(str, Enum):
    """Scope of the analysis requested."""
    SINGLE_LAP = "single_lap"       # One specific lap
    STINT = "stint"                  # One tire stint
    FULL_RACE = "full_race"          # Entire race
    MULTI_RACE = "multi_race"        # Multiple races/season
    QUALIFYING = "qualifying"        # Qualifying session
    PRACTICE = "practice"            # Practice session


class AnalysisType(str, Enum):
    """Type of analysis requested."""
    COMPARISON = "comparison"        # Driver vs driver
    STRATEGY = "strategy"            # Pit stops, tire choice
    PACE = "pace"                    # Lap times, consistency
    TELEMETRY = "telemetry"          # Speed traces, braking
    INCIDENT = "incident"            # Crashes, penalties
    PREDICTION = "prediction"        # What-if scenarios
    RESULTS = "results"              # Race results, standings
    GENERAL = "general"              # General F1 knowledge


class QueryUnderstanding(BaseModel):
    """Output of the UNDERSTAND node - parsed user intent."""

    query_type: AnalysisType = Field(
        description="Primary type of analysis requested"
    )
    scope: AnalysisScope = Field(
        description="Scope of data needed (single lap, full race, etc.)"
    )
    drivers: list[str] = Field(
        default_factory=list,
        description="Driver codes (3-letter, e.g., VER, NOR)"
    )
    teams: list[str] = Field(
        default_factory=list,
        description="Team names mentioned"
    )
    races: list[str] = Field(
        default_factory=list,
        description="Race names with year, e.g., 'Monaco 2024'"
    )
    seasons: list[int] = Field(
        default_factory=list,
        description="Years/seasons mentioned"
    )
    metrics: list[str] = Field(
        default_factory=list,
        description="Specific metrics requested (lap_time, tire_deg, etc.)"
    )
    sub_queries: list[str] = Field(
        default_factory=list,
        description="Decomposed sub-questions for complex queries"
    )
    hypothetical_answer: str = Field(
        default="",
        description="HyDE - what an ideal comprehensive answer would cover"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in query understanding (0-1)"
    )


class ToolCall(BaseModel):
    """Single tool invocation in the execution plan."""

    id: str = Field(description="Unique identifier for this tool call")
    tool_name: str = Field(description="Name of the tool to invoke")
    parameters: dict = Field(
        default_factory=dict,
        description="Parameters to pass to the tool"
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of tool calls this depends on"
    )
    purpose: str = Field(
        default="",
        description="Why this tool is being called"
    )


class DataPlan(BaseModel):
    """Output of the PLAN node - execution plan for data retrieval."""

    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="List of tools to call"
    )
    parallel_groups: list[list[str]] = Field(
        default_factory=list,
        description="Groups of tool IDs that can run concurrently"
    )
    expected_data_points: int = Field(
        default=0,
        description="Expected number of data points to retrieve"
    )
    reasoning: str = Field(
        default="",
        description="Explanation of why these tools were chosen"
    )
