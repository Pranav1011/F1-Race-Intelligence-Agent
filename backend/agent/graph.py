"""
Agent Graph

Enhanced LangGraph graph definition for the F1 Race Intelligence Agent.

Architecture:
UNDERSTAND → PLAN → EXECUTE → PROCESS → EVALUATE → ENRICH → GENERATE → VALIDATE → END
                                          ↓
                                    [is_sufficient?]
                                    NO → back to PLAN (CRAG pattern)
                                    YES → ENRICH → GENERATE → VALIDATE → END

Nodes:
- UNDERSTAND: Parse query, extract entities, generate HyDE
- PLAN: Create tool execution DAG with parallel groups
- EXECUTE: Run tools concurrently
- PROCESS: Aggregate raw data into analysis
- EVALUATE: Check data quality (CRAG loop if insufficient)
- ENRICH: Fetch RAG context (race reports, Reddit, regulations)
- GENERATE: Create response with visualization using enriched context
- VALIDATE: Verify response quality before returning

Memory Integration:
- User context is loaded from Mem0 before UNDERSTAND
- Conversation is stored to Mem0 after GENERATE
- Session context is maintained in Redis

Observability:
- Langfuse tracing for LLM calls and agent flow
- Sentry error capture for exceptions
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
    enrich_context,
    generate_response,
    validate_response,
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
    graph.add_node("enrich", enrich_context)
    graph.add_node("generate", partial(_generate_node, llm_router=llm_router))
    graph.add_node("validate", partial(_validate_node, llm_router=llm_router))

    # Set entry point
    graph.set_entry_point("understand")

    # Add edges for the main flow
    graph.add_edge("understand", "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "process")
    graph.add_edge("process", "evaluate")

    # Add conditional edge from evaluate (CRAG pattern)
    # If data is insufficient, loop back to plan
    # If sufficient, continue to enrich (then generate)
    graph.add_conditional_edges(
        "evaluate",
        should_continue,
        {
            "plan": "plan",      # Loop back for more data
            "generate": "enrich",  # Continue to enrich with RAG context
        },
    )

    # Enrich → Generate → Validate → END
    graph.add_edge("enrich", "generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)

    logger.info("Enhanced agent graph created with ENRICH and VALIDATE nodes")
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


async def _validate_node(
    state: EnhancedAgentState,
    llm_router: LLMRouter,
) -> dict[str, Any]:
    """Wrapper for validate_response node."""
    return await validate_response(state, llm_router)


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
    - Memory integration (Mem0 + Redis)
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        deepseek_api_key: str | None = None,
        groq_api_key: str | None = None,
        google_api_key: str | None = None,
        ollama_base_url: str = "http://ollama:11434",
        # Memory configuration
        enable_memory: bool = True,
        qdrant_host: str = "qdrant",
        qdrant_port: int = 6333,
        redis_host: str = "redis",
        redis_port: int = 6379,
        memory_llm_provider: str = "ollama",
    ):
        """
        Initialize the F1 Agent.

        Args:
            openai_api_key: OpenAI API key (primary LLM - GPT-4)
            deepseek_api_key: DeepSeek API key (backup - good reasoning)
            groq_api_key: Groq API key (fast backup)
            google_api_key: Google API key (backup LLM)
            ollama_base_url: Ollama server URL (local fallback)
            enable_memory: Whether to enable memory system
            qdrant_host: Qdrant host for Mem0
            qdrant_port: Qdrant port
            redis_host: Redis host for session state
            redis_port: Redis port
            memory_llm_provider: LLM provider for Mem0 memory extraction
        """
        self.config = LLMConfig(
            openai_api_key=openai_api_key,
            deepseek_api_key=deepseek_api_key,
            groq_api_key=groq_api_key,
            google_api_key=google_api_key,
            ollama_base_url=ollama_base_url,
        )
        self.graph = create_enhanced_agent_graph(self.config)
        self._sessions: dict[str, EnhancedAgentState] = {}

        # Memory configuration
        self.enable_memory = enable_memory
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.memory_llm_provider = memory_llm_provider
        self.ollama_base_url = ollama_base_url

        # Memory instances (initialized lazily)
        self._user_memory = None
        self._session_state = None

        logger.info(f"F1Agent initialized with enhanced architecture (memory={enable_memory})")

    async def _get_user_memory(self):
        """Get or create user memory instance."""
        if self._user_memory is None and self.enable_memory:
            try:
                from memory.user_memory import UserMemory
                self._user_memory = UserMemory(
                    qdrant_host=self.qdrant_host,
                    qdrant_port=self.qdrant_port,
                    llm_provider=self.memory_llm_provider,
                    llm_config={"ollama_base_url": self.ollama_base_url},
                )
                self._user_memory.initialize()
                logger.info("UserMemory initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize UserMemory: {e}")
                self._user_memory = None
        return self._user_memory

    async def _get_session_state(self):
        """Get or create session state instance."""
        if self._session_state is None and self.enable_memory:
            try:
                from memory.session_state import SessionState
                self._session_state = SessionState(
                    redis_host=self.redis_host,
                    redis_port=self.redis_port,
                )
                await self._session_state.initialize()
                logger.info("SessionState initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize SessionState: {e}")
                self._session_state = None
        return self._session_state

    def get_or_create_session(
        self,
        session_id: str,
        user_id: str | None = None,
        user_context: str = "",
        session_context: dict | None = None,
    ) -> EnhancedAgentState:
        """Get existing session or create new one."""
        if session_id not in self._sessions:
            self._sessions[session_id] = create_initial_state(
                session_id, user_id, user_context, session_context
            )
        return self._sessions[session_id]

    async def chat(
        self,
        message: str,
        session_id: str,
        user_id: str | None = None,
        status_callback = None,
    ) -> dict[str, Any]:
        """
        Process a user message and generate a response.

        The enhanced agent flow:
        0. MEMORY: Load user context from Mem0, session context from Redis
        1. UNDERSTAND: Parse query, extract entities, generate HyDE
        2. PLAN: Create tool execution DAG with parallel groups
        3. EXECUTE: Run tools concurrently
        4. PROCESS: Aggregate raw data into analysis
        5. EVALUATE: Check data quality (CRAG loop if insufficient)
        6. GENERATE: Create response with visualization
        7. MEMORY: Store conversation to Mem0 for future context

        Args:
            message: User's message
            session_id: Session identifier
            user_id: Optional user identifier
            status_callback: Optional async callback for status updates (stage, message)

        Returns:
            Response dict with analysis, visualization, and metadata
        """
        # Helper to send status if callback is provided
        async def send_status(stage: str, message: str):
            if status_callback:
                try:
                    await status_callback(stage, message)
                except Exception as e:
                    logger.debug(f"Status callback error: {e}")
        logger.info(f"Processing message in session {session_id}")

        # Load memory context
        user_context = ""
        session_context = {}

        if self.enable_memory and user_id:
            try:
                user_memory = await self._get_user_memory()
                if user_memory:
                    user_context = await user_memory.get_user_context(user_id, message)
                    logger.debug(f"Loaded user context: {len(user_context)} chars")
            except Exception as e:
                logger.warning(f"Error loading user context: {e}")

        if self.enable_memory:
            try:
                session_state = await self._get_session_state()
                if session_state:
                    session_context = await session_state.get_context(session_id) or {}
                    # Track message in Redis
                    await session_state.add_message(session_id, "user", message)
            except Exception as e:
                logger.warning(f"Error loading session context: {e}")

        # Get or create session state
        state = self.get_or_create_session(session_id, user_id, user_context, session_context)

        # Add user message
        state["messages"].append(HumanMessage(content=message))

        # Get Langfuse callback handler for tracing
        langfuse_handler = None
        try:
            from observability.langfuse_tracer import get_langfuse_handler
            langfuse_handler = get_langfuse_handler(
                session_id=session_id,
                user_id=user_id,
                trace_name="f1-agent-chat",
                metadata={
                    "message_preview": message[:100],
                },
            )
        except Exception as e:
            logger.debug(f"Langfuse handler not available: {e}")

        try:
            # Run the enhanced graph with streaming for status updates
            config = {}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]

            # Map node names to F1 pit wall radio style status messages
            node_status_messages = {
                "understand": ("understanding", "Copy, we are checking..."),
                "plan": ("planning", "Analyzing strategy... Plan A, B, or C?"),
                "execute": ("executing", "Braking late into the data..."),
                "process": ("processing", "Overtaking from the outside..."),
                "evaluate": ("evaluating", "Box box, we are getting to you..."),
                "enrich": ("enriching", "Adding context, stay focused..."),
                "generate": ("generating", "Hammer time, composing response..."),
                "validate": ("validating", "Final sector, P1 in sight..."),
            }

            # Stream through the graph nodes for live status updates
            result = state
            async for event in self.graph.astream(state, config=config, stream_mode="updates"):
                # event is a dict with node name as key
                for node_name, node_output in event.items():
                    result.update(node_output)
                    # Send status update for this node
                    if node_name in node_status_messages:
                        stage, msg = node_status_messages[node_name]
                        await send_status(stage, msg)

            # Update session state
            self._sessions[session_id] = result

            # Extract query understanding for response
            understanding = result.get("query_understanding", {})
            evaluation = result.get("evaluation", {})
            validation = result.get("validation_result", {})
            analysis_result = result.get("analysis_result", "")

            # Store to memory (async, don't block response)
            if self.enable_memory and user_id:
                try:
                    user_memory = await self._get_user_memory()
                    if user_memory:
                        # Store the conversation for memory extraction
                        await user_memory.add_memory(
                            user_id=user_id,
                            messages=[
                                {"role": "user", "content": message},
                                {"role": "assistant", "content": analysis_result[:500]},
                            ],
                            metadata={
                                "session_id": session_id,
                                "query_type": understanding.get("query_type"),
                            },
                        )
                except Exception as e:
                    logger.warning(f"Error storing to user memory: {e}")

            if self.enable_memory:
                try:
                    session_state = await self._get_session_state()
                    if session_state:
                        await session_state.add_message(
                            session_id, "assistant", analysis_result[:500]
                        )
                        # Update context with current entities
                        await session_state.update_context(session_id, {
                            "last_query_type": understanding.get("query_type"),
                            "drivers": understanding.get("drivers", []),
                            "races": understanding.get("races", []),
                        })
                except Exception as e:
                    logger.warning(f"Error updating session state: {e}")

            # Build response
            response = {
                "message": analysis_result,
                "query_type": understanding.get("query_type", "unknown"),
                "response_type": result.get("response_type", "TEXT"),
                "visualization": result.get("visualization_spec"),
                "confidence": evaluation.get("score", 0.0),
                "validation_score": validation.get("score", 0.0) if validation else None,
                "validation_issues": validation.get("issues", []) if validation else [],
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
    openai_api_key: str | None = None,
    deepseek_api_key: str | None = None,
    groq_api_key: str | None = None,
    google_api_key: str | None = None,
    ollama_base_url: str = "http://ollama:11434",
    enable_memory: bool = True,
    qdrant_host: str = "qdrant",
    redis_host: str = "redis",
) -> F1Agent:
    """
    Get or create the singleton F1Agent instance.

    Args:
        openai_api_key: OpenAI API key (primary - GPT-4)
        deepseek_api_key: DeepSeek API key (backup)
        groq_api_key: Groq API key (fast backup)
        google_api_key: Google API key
        ollama_base_url: Ollama server URL
        enable_memory: Whether to enable memory system
        qdrant_host: Qdrant host for Mem0
        redis_host: Redis host for session state

    Returns:
        F1Agent instance
    """
    global _agent
    if _agent is None:
        _agent = F1Agent(
            openai_api_key=openai_api_key,
            deepseek_api_key=deepseek_api_key,
            groq_api_key=groq_api_key,
            google_api_key=google_api_key,
            ollama_base_url=ollama_base_url,
            enable_memory=enable_memory,
            qdrant_host=qdrant_host,
            redis_host=redis_host,
        )
    return _agent
