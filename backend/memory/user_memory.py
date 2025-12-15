"""User Memory via Mem0.

Provides long-term memory for user preferences, facts, and conversation context.
Uses Qdrant for vector storage and supports multiple LLM backends.
"""

import logging
from typing import Any

from mem0 import Memory

logger = logging.getLogger(__name__)


class UserMemory:
    """
    User memory manager using Mem0.

    Stores and retrieves:
    - User preferences (favorite drivers, teams, analysis styles)
    - Facts about the user's F1 knowledge level
    - Conversation context and history
    """

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "user_memories",
        llm_provider: str = "ollama",
        llm_config: dict | None = None,
        embedding_dims: int = 768,
    ):
        """
        Initialize user memory.

        Args:
            qdrant_host: Qdrant server host
            qdrant_port: Qdrant server port
            collection_name: Collection name for memories
            llm_provider: LLM provider (ollama, groq, openai, etc.)
            llm_config: Provider-specific LLM config
            embedding_dims: Embedding dimensions (768 for bge-base)
        """
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.collection_name = collection_name
        self.llm_provider = llm_provider
        self.llm_config = llm_config or {}
        self.embedding_dims = embedding_dims

        self._memory: Memory | None = None
        self._initialized = False

    def _build_config(self) -> dict:
        """Build Mem0 configuration."""
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": self.collection_name,
                    "host": self.qdrant_host,
                    "port": self.qdrant_port,
                    "embedding_model_dims": self.embedding_dims,
                },
            },
            "llm": {
                "provider": self.llm_provider,
                "config": self._get_llm_config(),
            },
            # Use Ollama for embeddings too (avoids OpenAI dependency)
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": "nomic-embed-text",
                    "ollama_base_url": self.llm_config.get(
                        "ollama_base_url", "http://ollama:11434"
                    ),
                },
            },
        }
        return config

    def _get_llm_config(self) -> dict:
        """Get provider-specific LLM config."""
        if self.llm_provider == "ollama":
            return {
                "model": self.llm_config.get("model", "llama3.2"),
                "ollama_base_url": self.llm_config.get(
                    "ollama_base_url", "http://ollama:11434"
                ),
                "temperature": self.llm_config.get("temperature", 0.1),
            }
        elif self.llm_provider == "groq":
            return {
                "model": self.llm_config.get("model", "llama-3.3-70b-versatile"),
                "api_key": self.llm_config.get("api_key"),
                "temperature": self.llm_config.get("temperature", 0.1),
            }
        elif self.llm_provider == "google":
            return {
                "model": self.llm_config.get("model", "gemini-2.0-flash-exp"),
                "api_key": self.llm_config.get("api_key"),
                "temperature": self.llm_config.get("temperature", 0.1),
            }
        else:
            return self.llm_config

    def initialize(self):
        """Initialize the Mem0 memory system."""
        if self._initialized:
            return

        logger.info(f"Initializing UserMemory with {self.llm_provider}...")
        config = self._build_config()

        try:
            self._memory = Memory.from_config(config)
            self._initialized = True
            logger.info("UserMemory initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize UserMemory: {e}")
            raise

    async def add_memory(
        self,
        user_id: str,
        messages: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> list[dict]:
        """
        Add memories from a conversation.

        Mem0 will automatically extract relevant facts and preferences
        from the messages.

        Args:
            user_id: User identifier
            messages: List of messages [{"role": "user/assistant", "content": "..."}]
            metadata: Optional metadata to attach

        Returns:
            List of extracted memories
        """
        if not self._initialized:
            self.initialize()

        try:
            result = self._memory.add(
                messages=messages,
                user_id=user_id,
                metadata=metadata or {},
            )
            logger.debug(f"Added memories for user {user_id}: {result}")
            return result.get("results", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.error(f"Error adding memory for user {user_id}: {e}")
            return []

    async def search_memories(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Search for relevant memories.

        Args:
            user_id: User identifier
            query: Search query
            limit: Maximum results

        Returns:
            List of relevant memories with scores
        """
        if not self._initialized:
            self.initialize()

        try:
            results = self._memory.search(
                query=query,
                user_id=user_id,
                limit=limit,
            )
            logger.debug(f"Found {len(results)} memories for query: {query[:50]}...")
            return results
        except Exception as e:
            logger.error(f"Error searching memories for user {user_id}: {e}")
            return []

    async def get_all_memories(self, user_id: str) -> list[dict]:
        """
        Get all memories for a user.

        Args:
            user_id: User identifier

        Returns:
            List of all memories
        """
        if not self._initialized:
            self.initialize()

        try:
            result = self._memory.get_all(user_id=user_id)
            memories = result.get("results", []) if isinstance(result, dict) else result
            logger.debug(f"Retrieved {len(memories)} memories for user {user_id}")
            return memories
        except Exception as e:
            logger.error(f"Error getting memories for user {user_id}: {e}")
            return []

    async def get_memory(self, memory_id: str) -> dict | None:
        """
        Get a specific memory by ID.

        Args:
            memory_id: Memory identifier

        Returns:
            Memory dict or None
        """
        if not self._initialized:
            self.initialize()

        try:
            return self._memory.get(memory_id=memory_id)
        except Exception as e:
            logger.error(f"Error getting memory {memory_id}: {e}")
            return None

    async def update_memory(
        self,
        memory_id: str,
        data: str,
    ) -> dict | None:
        """
        Update a specific memory.

        Args:
            memory_id: Memory identifier
            data: New memory content

        Returns:
            Updated memory or None
        """
        if not self._initialized:
            self.initialize()

        try:
            return self._memory.update(memory_id=memory_id, data=data)
        except Exception as e:
            logger.error(f"Error updating memory {memory_id}: {e}")
            return None

    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a specific memory.

        Args:
            memory_id: Memory identifier

        Returns:
            True if deleted
        """
        if not self._initialized:
            self.initialize()

        try:
            self._memory.delete(memory_id=memory_id)
            return True
        except Exception as e:
            logger.error(f"Error deleting memory {memory_id}: {e}")
            return False

    async def delete_all_memories(self, user_id: str) -> bool:
        """
        Delete all memories for a user.

        Args:
            user_id: User identifier

        Returns:
            True if deleted
        """
        if not self._initialized:
            self.initialize()

        try:
            self._memory.delete_all(user_id=user_id)
            logger.info(f"Deleted all memories for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting memories for user {user_id}: {e}")
            return False

    async def get_user_context(self, user_id: str, query: str) -> str:
        """
        Get formatted user context for a query.

        Combines relevant memories into a context string for the agent.

        Args:
            user_id: User identifier
            query: Current user query

        Returns:
            Formatted context string
        """
        memories = await self.search_memories(user_id, query, limit=5)

        if not memories:
            return ""

        context_parts = ["## User Context (from memory)"]
        for mem in memories:
            # Handle both string and dict return types from Mem0
            if isinstance(mem, str):
                memory_text = mem
            else:
                memory_text = mem.get("memory", mem.get("text", str(mem)))
            if memory_text:
                context_parts.append(f"- {memory_text}")

        return "\n".join(context_parts)

    def health_check(self) -> bool:
        """Check if memory system is healthy."""
        try:
            if not self._initialized:
                return False
            # Try a simple operation
            return self._memory is not None
        except Exception:
            return False


# Global instance
_user_memory: UserMemory | None = None


def get_user_memory(
    qdrant_host: str = "qdrant",
    qdrant_port: int = 6333,
    llm_provider: str = "ollama",
    llm_config: dict | None = None,
) -> UserMemory:
    """Get or create the global UserMemory instance."""
    global _user_memory
    if _user_memory is None:
        _user_memory = UserMemory(
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            llm_provider=llm_provider,
            llm_config=llm_config,
        )
        _user_memory.initialize()
    return _user_memory
