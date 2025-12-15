"""Memory tools for the F1 Agent.

Provides LangChain-compatible tools for:
- Recalling user preferences and facts
- Storing new information about the user
- Managing session context
"""

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from memory.user_memory import UserMemory
from memory.session_state import SessionState

logger = logging.getLogger(__name__)


# =========================================
# Tool Input Schemas
# =========================================


class RecallPreferencesInput(BaseModel):
    """Input for recalling user preferences."""

    query: str = Field(
        description="What to search for in user memories (e.g., 'favorite driver', 'preferred analysis style')"
    )


class StoreFactInput(BaseModel):
    """Input for storing a fact about the user."""

    fact: str = Field(
        description="The fact to remember about the user (e.g., 'User supports Ferrari', 'User prefers detailed tire analysis')"
    )


class GetContextInput(BaseModel):
    """Input for getting session context."""

    context_type: str = Field(
        default="all",
        description="Type of context to retrieve: 'all', 'drivers', 'race', 'analysis'"
    )


class UpdateContextInput(BaseModel):
    """Input for updating session context."""

    key: str = Field(description="Context key to update")
    value: Any = Field(description="Value to store")


# =========================================
# Memory Tools Factory
# =========================================


class MemoryTools:
    """
    Factory for creating memory-related tools.

    Tools allow the agent to:
    - Remember user preferences across sessions
    - Store facts learned during conversation
    - Maintain working context within a session
    """

    def __init__(
        self,
        user_memory: UserMemory,
        session_state: SessionState,
        user_id: str | None = None,
        session_id: str | None = None,
    ):
        """
        Initialize memory tools.

        Args:
            user_memory: UserMemory instance (Mem0)
            session_state: SessionState instance (Redis)
            user_id: Current user ID
            session_id: Current session ID
        """
        self.user_memory = user_memory
        self.session_state = session_state
        self.user_id = user_id
        self.session_id = session_id

    def set_user_id(self, user_id: str):
        """Set the current user ID."""
        self.user_id = user_id

    def set_session_id(self, session_id: str):
        """Set the current session ID."""
        self.session_id = session_id

    async def recall_preferences(self, query: str) -> str:
        """
        Recall user preferences and facts from long-term memory.

        Args:
            query: What to search for

        Returns:
            Formatted string of relevant memories
        """
        if not self.user_id:
            return "No user context available - cannot recall preferences."

        try:
            memories = await self.user_memory.search_memories(
                user_id=self.user_id,
                query=query,
                limit=5,
            )

            if not memories:
                return f"No memories found related to: {query}"

            result_parts = [f"User memories related to '{query}':"]
            for i, mem in enumerate(memories, 1):
                # Handle both string and dict return types from Mem0
                if isinstance(mem, str):
                    memory_text = mem
                    score = 0
                else:
                    memory_text = mem.get("memory", mem.get("text", str(mem)))
                    score = mem.get("score", 0)
                if memory_text:
                    result_parts.append(f"{i}. {memory_text} (relevance: {score:.2f})")

            return "\n".join(result_parts)

        except Exception as e:
            logger.error(f"Error recalling preferences: {e}")
            return f"Error retrieving memories: {str(e)}"

    async def store_fact(self, fact: str) -> str:
        """
        Store a fact about the user for future reference.

        Args:
            fact: The fact to remember

        Returns:
            Confirmation message
        """
        if not self.user_id:
            return "No user context available - cannot store fact."

        try:
            # Store as a simple user message that Mem0 will extract facts from
            messages = [
                {"role": "assistant", "content": f"I learned that: {fact}"},
            ]

            result = await self.user_memory.add_memory(
                user_id=self.user_id,
                messages=messages,
                metadata={"source": "agent_observation"},
            )

            if result:
                return f"Remembered: {fact}"
            return f"Stored fact: {fact}"

        except Exception as e:
            logger.error(f"Error storing fact: {e}")
            return f"Error storing fact: {str(e)}"

    async def get_session_context(self, context_type: str = "all") -> str:
        """
        Get current session context.

        Args:
            context_type: Type of context to retrieve

        Returns:
            Formatted context string
        """
        if not self.session_id:
            return "No session context available."

        try:
            context = await self.session_state.get_context(self.session_id)

            if not context:
                return "No context set for this session."

            if context_type == "all":
                return f"Session context: {context}"

            if context_type in context:
                return f"{context_type}: {context[context_type]}"

            return f"No '{context_type}' in session context."

        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return f"Error retrieving context: {str(e)}"

    async def update_session_context(self, key: str, value: Any) -> str:
        """
        Update session context with new information.

        Args:
            key: Context key
            value: Value to store

        Returns:
            Confirmation message
        """
        if not self.session_id:
            return "No session available - cannot update context."

        try:
            await self.session_state.update_context(
                self.session_id,
                {key: value},
            )
            return f"Updated context: {key} = {value}"

        except Exception as e:
            logger.error(f"Error updating context: {e}")
            return f"Error updating context: {str(e)}"

    def get_tools(self) -> list[StructuredTool]:
        """
        Get list of LangChain-compatible tools.

        Returns:
            List of StructuredTool objects
        """
        return [
            StructuredTool(
                name="recall_user_preferences",
                description=(
                    "Search user's long-term memory for preferences, facts, and past interactions. "
                    "Use this to personalize responses based on what you know about the user. "
                    "Example queries: 'favorite driver', 'preferred teams', 'analysis preferences'"
                ),
                func=lambda **kwargs: None,  # Sync placeholder
                coroutine=self.recall_preferences,
                args_schema=RecallPreferencesInput,
            ),
            StructuredTool(
                name="store_user_fact",
                description=(
                    "Store a fact or preference about the user for future reference. "
                    "Use this when the user explicitly states a preference or you learn something "
                    "important about them. Examples: 'User supports Ferrari', 'User prefers lap-by-lap analysis'"
                ),
                func=lambda **kwargs: None,
                coroutine=self.store_fact,
                args_schema=StoreFactInput,
            ),
            StructuredTool(
                name="get_session_context",
                description=(
                    "Get the current session's working context. This includes drivers being discussed, "
                    "current race/session, analysis type, and other temporary state."
                ),
                func=lambda **kwargs: None,
                coroutine=self.get_session_context,
                args_schema=GetContextInput,
            ),
            StructuredTool(
                name="update_session_context",
                description=(
                    "Update the current session's working context. Use this to track entities "
                    "being discussed, current analysis focus, etc."
                ),
                func=lambda **kwargs: None,
                coroutine=self.update_session_context,
                args_schema=UpdateContextInput,
            ),
        ]


# =========================================
# Convenience Functions
# =========================================


async def create_memory_tools(
    user_memory: UserMemory,
    session_state: SessionState,
    user_id: str | None = None,
    session_id: str | None = None,
) -> list[StructuredTool]:
    """
    Create memory tools for the agent.

    Args:
        user_memory: UserMemory instance
        session_state: SessionState instance
        user_id: Optional user ID
        session_id: Optional session ID

    Returns:
        List of LangChain tools
    """
    factory = MemoryTools(
        user_memory=user_memory,
        session_state=session_state,
        user_id=user_id,
        session_id=session_id,
    )
    return factory.get_tools()


async def get_user_context_for_query(
    user_memory: UserMemory,
    user_id: str,
    query: str,
) -> str:
    """
    Get formatted user context for injecting into prompts.

    Args:
        user_memory: UserMemory instance
        user_id: User identifier
        query: Current user query

    Returns:
        Formatted context string or empty string
    """
    return await user_memory.get_user_context(user_id, query)
