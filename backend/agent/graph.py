"""
Agent Graph

Enhanced LangGraph graph definition for the F1 Race Intelligence Agent.

Architecture:
UNDERSTAND → PLAN → EXECUTE → PROCESS → EVALUATE → GENERATE
                                          ↓
                                    [is_sufficient?]
                                    NO → back to PLAN (CRAG pattern)
                                    YES → GENERATE → END
"""

import logging
from functools import partial
from typing import Any

from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage

from agent.state import EnhancedAgentState, create_initial_state
from agent.llm import LLMRouter, LLMConfig
from agent.nodes import (
    understand_query,
    plan_data_retrieval,
    execute_tools,
    process_data,
    evaluate_data,
    should_continue,
    generate_response,
)
from agent.tools.timescale_tools import TIMESCALE_TOOLS
from agent.tools.neo4j_tools import NEO4J_TOOLS
from agent.tools.vector_tools import VECTOR_TOOLS

logger = logging.getLogger(__name__)


def create_enhanced_agent_graph(
    llm_config: LLMConfig | None = None,
) -> StateGraph:
    """
    Create the enhanced F1 Race Intelligence Agent graph.

    Features:
    - CRAG pattern with EVALUATE loop for data quality
    - Parallel tool execution in EXECUTE node
    - Pydantic-validated structured outputs
    - HyDE for vague queries
    - Query decomposition for complex questions

    Args:
        llm_config: LLM configuration (uses env vars if not provided)

    Returns:
        Compiled LangGraph StateGraph
    """
    logger.info("Creating enhanced agent graph")

    # Initialize LLM router
    llm_router = LLMRouter(llm_config)

    # Create the graph with enhanced state
    graph = StateGraph(EnhancedAgentState)

    # Add nodes with their dependencies
    graph.add_node("understand", partial(_understand_node, llm_router=llm_router))
    graph.add_node("plan", partial(_plan_node, llm_router=llm_router))
    graph.add_node("execute", _execute_node)
    graph.add_node("process", process_data)
    graph.add_node("evaluate", evaluate_data)
    graph.add_node("generate", partial(_generate_node, llm_router=llm_router))

    # Set entry point
    graph.set_entry_point("understand")

    # Add edges for the main flow
    graph.add_edge("understand", "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "process")
    graph.add_edge("process", "evaluate")

    # Add conditional edge from evaluate (CRAG pattern)
    # If data is insufficient, loop back to plan
    # If sufficient, continue to generate
    graph.add_conditional_edges(
        "evaluate",
        should_continue,
        {
            "plan": "plan",      # Loop back for more data
            "generate": "generate",  # Continue to response
        },
    )

    # Final edge to end
    graph.add_edge("generate", END)

    logger.info("Enhanced agent graph created with CRAG evaluation loop")
    return graph.compile()


async def _understand_node(
    state: EnhancedAgentState,
    llm_router: LLMRouter,
) -> dict[str, Any]:
    """Wrapper for understand_query node."""
    return await understand_query(state, llm_router)


async def _plan_node(
    state: EnhancedAgentState,
    llm_router: LLMRouter,
) -> dict[str, Any]:
    """Wrapper for plan_data_retrieval node."""
    return await plan_data_retrieval(state, llm_router)


async def _execute_node(state: EnhancedAgentState) -> dict[str, Any]:
    """Wrapper for execute_tools node."""
    return await execute_tools(
        state,
        timescale_tools=TIMESCALE_TOOLS,
        neo4j_tools=NEO4J_TOOLS,
        vector_tools=VECTOR_TOOLS,
    )


async def _generate_node(
    state: EnhancedAgentState,
    llm_router: LLMRouter,
) -> dict[str, Any]:
    """Wrapper for generate_response node."""
    return await generate_response(state, llm_router)


# Keep old function name for backwards compatibility
create_agent_graph = create_enhanced_agent_graph


class F1Agent:
    """
    High-level interface for the F1 Race Intelligence Agent.

    Enhanced with:
    - CRAG pattern for data quality assurance
    - Parallel tool execution
    - Structured Pydantic outputs
    - Visualization specification generation
    """

    def __init__(
        self,
        deepseek_api_key: str | None = None,
        groq_api_key: str | None = None,
        google_api_key: str | None = None,
        ollama_base_url: str = "http://ollama:11434",
    ):
        """
        Initialize the F1 Agent.

        Args:
            deepseek_api_key: DeepSeek API key (primary LLM - best reasoning)
            groq_api_key: Groq API key (fast backup)
            google_api_key: Google API key (backup LLM)
            ollama_base_url: Ollama server URL (local fallback)
        """
        self.config = LLMConfig(
            deepseek_api_key=deepseek_api_key,
            groq_api_key=groq_api_key,
            google_api_key=google_api_key,
            ollama_base_url=ollama_base_url,
        )
        self.graph = create_enhanced_agent_graph(self.config)
        self._sessions: dict[str, EnhancedAgentState] = {}
        logger.info("F1Agent initialized with enhanced architecture")

    def get_or_create_session(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> EnhancedAgentState:
        """Get existing session or create new one."""
        if session_id not in self._sessions:
            self._sessions[session_id] = create_initial_state(session_id, user_id)
        return self._sessions[session_id]

    async def chat(
        self,
        message: str,
        session_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Process a user message and generate a response.

        The enhanced agent flow:
        1. UNDERSTAND: Parse query, extract entities, generate HyDE
        2. PLAN: Create tool execution DAG with parallel groups
        3. EXECUTE: Run tools concurrently
        4. PROCESS: Aggregate raw data into analysis
        5. EVALUATE: Check data quality (CRAG loop if insufficient)
        6. GENERATE: Create response with visualization

        Args:
            message: User's message
            session_id: Session identifier
            user_id: Optional user identifier

        Returns:
            Response dict with analysis, visualization, and metadata
        """
        logger.info(f"Processing message in session {session_id}")

        # Get or create session state
        state = self.get_or_create_session(session_id, user_id)

        # Add user message
        state["messages"].append(HumanMessage(content=message))

        try:
            # Run the enhanced graph
            result = await self.graph.ainvoke(state)

            # Update session state
            self._sessions[session_id] = result

            # Extract query understanding for response
            understanding = result.get("query_understanding", {})
            evaluation = result.get("evaluation", {})

            # Build response
            response = {
                "message": result.get("analysis_result", ""),
                "query_type": understanding.get("query_type", "unknown"),
                "response_type": result.get("response_type", "TEXT"),
                "visualization": result.get("visualization_spec"),
                "confidence": evaluation.get("score", 0.0),
                "iterations": result.get("iteration_count", 0),
                "session_id": session_id,
                "error": result.get("error"),
            }

            return response

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return {
                "message": f"I apologize, but I encountered an error: {str(e)}",
                "query_type": "error",
                "response_type": "TEXT",
                "visualization": None,
                "confidence": 0.0,
                "iterations": 0,
                "session_id": session_id,
                "error": str(e),
            }

    def get_session_history(self, session_id: str) -> list[dict]:
        """Get conversation history for a session."""
        state = self._sessions.get(session_id)
        if not state:
            return []

        history = []
        for msg in state.get("messages", []):
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            else:
                history.append({"role": "assistant", "content": msg.content})

        return history

    def get_session_analysis(self, session_id: str) -> dict | None:
        """Get the latest analysis for a session."""
        state = self._sessions.get(session_id)
        if not state:
            return None

        return {
            "query_understanding": state.get("query_understanding"),
            "processed_analysis": state.get("processed_analysis"),
            "evaluation": state.get("evaluation"),
            "visualization_spec": state.get("visualization_spec"),
        }

    def clear_session(self, session_id: str):
        """Clear a session's history."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Cleared session {session_id}")


# Singleton agent instance (initialized on first use)
_agent: F1Agent | None = None


def get_agent(
    deepseek_api_key: str | None = None,
    groq_api_key: str | None = None,
    google_api_key: str | None = None,
    ollama_base_url: str = "http://ollama:11434",
) -> F1Agent:
    """
    Get or create the singleton F1Agent instance.

    Args:
        deepseek_api_key: DeepSeek API key (primary)
        groq_api_key: Groq API key (fast backup)
        google_api_key: Google API key
        ollama_base_url: Ollama server URL

    Returns:
        F1Agent instance
    """
    global _agent
    if _agent is None:
        _agent = F1Agent(
            deepseek_api_key=deepseek_api_key,
            groq_api_key=groq_api_key,
            google_api_key=google_api_key,
            ollama_base_url=ollama_base_url,
        )
    return _agent
