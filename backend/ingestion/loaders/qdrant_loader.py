"""
Qdrant Vector Store Loader

Sets up Qdrant collections for RAG:
- race_reports: Journalist articles and post-race analysis
- reddit_discussions: Community discussions and insights
- regulations: FIA sporting and technical regulations
- past_analyses: Previous agent responses for learning
"""

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams

logger = logging.getLogger(__name__)

# Embedding dimensions for different models
EMBEDDING_DIMS = {
    "bge-base": 768,
    "bge-large": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

# Default embedding dimension (BGE base)
DEFAULT_EMBEDDING_DIM = 768


class QdrantLoader:
    """Set up and manage Qdrant collections for F1 RAG."""

    def __init__(self, host: str = "localhost", port: int = 6333):
        """
        Initialize the Qdrant loader.

        Args:
            host: Qdrant server host
            port: Qdrant server port
        """
        # Disable version check to support different server versions
        self.client = QdrantClient(host=host, port=port, check_compatibility=False)
        logger.info(f"Qdrant client initialized for {host}:{port}")

    def initialize(self, embedding_dim: int = DEFAULT_EMBEDDING_DIM):
        """
        Create all required collections with proper configuration.

        Args:
            embedding_dim: Dimension of embedding vectors
        """
        logger.info(f"Initializing Qdrant collections with {embedding_dim}-dim vectors")

        collections_config = {
            "race_reports": {
                "description": "Journalist articles and post-race analysis",
                "payload_schema": {
                    "source": models.PayloadSchemaType.KEYWORD,
                    "url": models.PayloadSchemaType.KEYWORD,
                    "race_id": models.PayloadSchemaType.KEYWORD,
                    "season": models.PayloadSchemaType.INTEGER,
                    "drivers": models.PayloadSchemaType.KEYWORD,
                    "teams": models.PayloadSchemaType.KEYWORD,
                    "topics": models.PayloadSchemaType.KEYWORD,
                    "published_date": models.PayloadSchemaType.DATETIME,
                },
            },
            "reddit_discussions": {
                "description": "Community discussions from r/formula1",
                "payload_schema": {
                    "post_id": models.PayloadSchemaType.KEYWORD,
                    "subreddit": models.PayloadSchemaType.KEYWORD,
                    "race_id": models.PayloadSchemaType.KEYWORD,
                    "season": models.PayloadSchemaType.INTEGER,
                    "score": models.PayloadSchemaType.INTEGER,
                    "drivers": models.PayloadSchemaType.KEYWORD,
                    "teams": models.PayloadSchemaType.KEYWORD,
                    "quality_score": models.PayloadSchemaType.FLOAT,
                },
            },
            "regulations": {
                "description": "FIA sporting and technical regulations",
                "payload_schema": {
                    "document_type": models.PayloadSchemaType.KEYWORD,
                    "section": models.PayloadSchemaType.KEYWORD,
                    "year": models.PayloadSchemaType.INTEGER,
                    "article_number": models.PayloadSchemaType.KEYWORD,
                },
            },
            "past_analyses": {
                "description": "Previous agent analyses for learning and reference",
                "payload_schema": {
                    "query": models.PayloadSchemaType.TEXT,
                    "query_type": models.PayloadSchemaType.KEYWORD,
                    "race_id": models.PayloadSchemaType.KEYWORD,
                    "drivers": models.PayloadSchemaType.KEYWORD,
                    "created_at": models.PayloadSchemaType.DATETIME,
                },
            },
        }

        for collection_name, config in collections_config.items():
            self._create_collection(collection_name, embedding_dim, config)

        logger.info("All Qdrant collections initialized")

    def _create_collection(
        self,
        name: str,
        embedding_dim: int,
        config: dict[str, Any],
    ):
        """Create a single collection if it doesn't exist."""
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            exists = any(c.name == name for c in collections)

            if exists:
                logger.debug(f"Collection '{name}' already exists")
                return

            # Create collection with vector configuration
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE,
                ),
            )

            # Create payload indexes for filtering
            for field_name, field_type in config.get("payload_schema", {}).items():
                try:
                    self.client.create_payload_index(
                        collection_name=name,
                        field_name=field_name,
                        field_schema=field_type,
                    )
                except Exception as e:
                    logger.debug(f"Index {field_name} may already exist: {e}")

            logger.info(f"Created collection '{name}': {config.get('description', '')}")

        except Exception as e:
            logger.error(f"Failed to create collection '{name}': {e}")
            raise

    def get_collection_info(self, name: str) -> dict:
        """Get information about a collection."""
        try:
            info = self.client.get_collection(name)
            # Handle different Qdrant API versions
            vectors_count = getattr(info, 'vectors_count', None)
            if vectors_count is None:
                # Older API uses points_count
                vectors_count = getattr(info, 'points_count', 0)
            return {
                "name": name,
                "vectors_count": vectors_count,
                "points_count": getattr(info, 'points_count', vectors_count),
                "status": str(info.status) if hasattr(info, 'status') else "unknown",
            }
        except Exception as e:
            logger.error(f"Failed to get collection info for '{name}': {e}")
            return {"name": name, "error": str(e)}

    def get_all_collections_info(self) -> list[dict]:
        """Get information about all collections."""
        collections = self.client.get_collections().collections
        return [self.get_collection_info(c.name) for c in collections]

    def delete_collection(self, name: str):
        """Delete a collection."""
        try:
            self.client.delete_collection(name)
            logger.info(f"Deleted collection '{name}'")
        except Exception as e:
            logger.error(f"Failed to delete collection '{name}': {e}")

    def health_check(self) -> bool:
        """Check if Qdrant is healthy."""
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False
