"""
F1 Race Intelligence Agent

Enhanced LangGraph-based conversational agent for F1 race analysis.

Architecture:
UNDERSTAND → PLAN → EXECUTE → PROCESS → EVALUATE → GENERATE
                                          ↓
                                    [CRAG loop if insufficient]
"""

from agent.graph import F1Agent, create_agent_graph, get_agent
from agent.state import EnhancedAgentState, AgentStateDict, create_initial_state
from agent.llm import LLMRouter, LLMConfig, LLMProvider

# Import Pydantic schemas for external use
from agent.schemas.query import (
    AnalysisType,
    AnalysisScope,
    QueryUnderstanding,
    DataPlan,
    ToolCall,
)
from agent.schemas.analysis import (
    ChartType,
    ProcessedAnalysis,
    LapAnalysis,
    StintSummary,
    DriverComparison,
    EvaluationResult,
)

__all__ = [
    # Agent
    "F1Agent",
    "create_agent_graph",
    "get_agent",
    # State
    "EnhancedAgentState",
    "AgentStateDict",
    "create_initial_state",
    # LLM
    "LLMRouter",
    "LLMConfig",
    "LLMProvider",
    # Schemas - Query
    "AnalysisType",
    "AnalysisScope",
    "QueryUnderstanding",
    "DataPlan",
    "ToolCall",
    # Schemas - Analysis
    "ChartType",
    "ProcessedAnalysis",
    "LapAnalysis",
    "StintSummary",
    "DriverComparison",
    "EvaluationResult",
]
