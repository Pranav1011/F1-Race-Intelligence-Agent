"""
Agent Graph

LangGraph graph definition for the F1 Race Intelligence Agent.
"""

import logging
from functools import partial
from typing import Any

from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage

from agent.state import AgentStateDict, create_initial_state
from agent.llm import LLMRouter, LLMConfig
from agent.nodes import (
    classify_query,
    retrieve_data,
    generate_response,
    should_retrieve,
    format_final_response,
)
from agent.tools.timescale_tools import TIMESCALE_TOOLS
from agent.tools.neo4j_tools import NEO4J_TOOLS
from agent.tools.vector_tools import VECTOR_TOOLS

logger = logging.getLogger(__name__)


def create_agent_graph(
    llm_config: LLMConfig | None = None,
) -> StateGraph:
    """
    Create the F1 Race Intelligence Agent graph.

    Args:
        llm_config: LLM configuration (uses env vars if not provided)

    Returns:
        Compiled LangGraph StateGraph
    """
    logger.info("Creating agent graph")

    # Initialize LLM router
    llm_router = LLMRouter(llm_config)

    # Create the graph
    graph = StateGraph(AgentStateDict)

    # Add nodes
    graph.add_node("classify", partial(_classify_node, llm_router=llm_router))
    graph.add_node("retrieve", partial(_retrieve_node))
    graph.add_node("generate", partial(_generate_node, llm_router=llm_router))
    graph.add_node("format", format_final_response)

    # Set entry point
    graph.set_entry_point("classify")

    # Add conditional edges
    graph.add_conditional_edges(
        "classify",
        should_retrieve,
        {
            "retrieve": "retrieve",
            "generate": "generate",
        },
    )

    # Add edges
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "format")
    graph.add_edge("format", END)

    logger.info("Agent graph created")
    return graph.compile()


async def _classify_node(state: AgentStateDict, llm_router: LLMRouter) -> AgentStateDict:
    """Wrapper for classify_query node."""
    return await classify_query(state, llm_router)


async def _retrieve_node(state: AgentStateDict) -> AgentStateDict:
    """Wrapper for retrieve_data node."""
    return await retrieve_data(
        state,
        timescale_tools=TIMESCALE_TOOLS,
        neo4j_tools=NEO4J_TOOLS,
        vector_tools=VECTOR_TOOLS,
    )


async def _generate_node(state: AgentStateDict, llm_router: LLMRouter) -> AgentStateDict:
    """Wrapper for generate_response node."""
    return await generate_response(state, llm_router)


class F1Agent:
    """
    High-level interface for the F1 Race Intelligence Agent.
    """

    def __init__(
        self,
        groq_api_key: str | None = None,
        google_api_key: str | None = None,
        ollama_base_url: str = "http://ollama:11434",
    ):
        """
        Initialize the F1 Agent.

        Args:
            groq_api_key: Groq API key (primary LLM)
            google_api_key: Google API key (backup LLM)
            ollama_base_url: Ollama server URL (local fallback)
        """
        self.config = LLMConfig(
            groq_api_key=groq_api_key,
            google_api_key=google_api_key,
            ollama_base_url=ollama_base_url,
        )
        self.graph = create_agent_graph(self.config)
        self._sessions: dict[str, AgentStateDict] = {}
        logger.info("F1Agent initialized")

    def get_or_create_session(self, session_id: str, user_id: str | None = None) -> AgentStateDict:
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

        Args:
            message: User's message
            session_id: Session identifier
            user_id: Optional user identifier

        Returns:
            Response dict with analysis and metadata
        """
        logger.info(f"Processing message in session {session_id}")

        # Get or create session state
        state = self.get_or_create_session(session_id, user_id)

        # Add user message
        state["messages"].append(HumanMessage(content=message))

        try:
            # Run the graph
            result = await self.graph.ainvoke(state)

            # Update session state
            self._sessions[session_id] = result

            # Extract response
            response = {
                "message": result.get("analysis_result", ""),
                "query_type": result.get("query_type", "unknown"),
                "response_type": result.get("response_type", "text"),
                "confidence": result.get("confidence", 0.0),
                "session_id": session_id,
                "error": result.get("error"),
            }

            return response

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {
                "message": f"I apologize, but I encountered an error: {str(e)}",
                "query_type": "error",
                "response_type": "text",
                "confidence": 0.0,
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

    def clear_session(self, session_id: str):
        """Clear a session's history."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Cleared session {session_id}")


# Singleton agent instance (initialized on first use)
_agent: F1Agent | None = None


def get_agent(
    groq_api_key: str | None = None,
    google_api_key: str | None = None,
    ollama_base_url: str = "http://ollama:11434",
) -> F1Agent:
    """
    Get or create the singleton F1Agent instance.

    Args:
        groq_api_key: Groq API key
        google_api_key: Google API key
        ollama_base_url: Ollama server URL

    Returns:
        F1Agent instance
    """
    global _agent
    if _agent is None:
        _agent = F1Agent(
            groq_api_key=groq_api_key,
            google_api_key=google_api_key,
            ollama_base_url=ollama_base_url,
        )
    return _agent
