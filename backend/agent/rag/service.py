"""
RAG Service for F1 Race Intelligence Agent.

Provides hybrid retrieval combining:
- Semantic search (dense embeddings via Qdrant)
- Keyword search (BM25 via full-text search)
- Cohere reranking for improved relevance

Collections:
- race_reports: Journalist articles and analysis
- regulations: FIA sporting and technical regulations
- past_analyses: Previous agent responses
"""

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams

from agent.rag.embeddings import EmbeddingService

logger = logging.getLogger(__name__)

# Optional Cohere reranker
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    logger.debug("Cohere not installed - reranking disabled")


@dataclass
class SearchResult:
    """A single search result."""

    content: str
    score: float
    metadata: dict[str, Any]
    source: str  # Collection name

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
            "source": self.source,
        }


@dataclass
class HybridSearchResult:
    """Combined result from hybrid search."""

    results: list[SearchResult]
    query: str
    semantic_weight: float
    keyword_weight: float


class RAGService:
    """
    RAG service with hybrid search capabilities.

    Combines semantic (dense) and keyword (sparse) search
    for improved retrieval quality.
    """

    # Collection configurations
    COLLECTIONS = {
        "race_reports": {
            "description": "Journalist articles and race analysis",
            "text_field": "content",
            "metadata_fields": ["source", "url", "race_id", "season", "drivers", "teams", "published_date"],
        },
        "reddit_discussions": {
            "description": "Reddit r/formula1 discussions",
            "text_field": "content",
            "metadata_fields": ["post_id", "race_id", "score", "quality_score", "subreddit", "created_at"],
        },
        "regulations": {
            "description": "FIA sporting and technical regulations",
            "text_field": "content",
            "metadata_fields": ["document_type", "section", "article_number", "year"],
        },
        "past_analyses": {
            "description": "Previous agent analyses",
            "text_field": "content",
            "metadata_fields": ["query", "query_type", "race_id", "drivers", "created_at"],
        },
    }

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        embedding_model: str = "BAAI/bge-base-en-v1.5",
        cohere_api_key: str | None = None,
        enable_reranking: bool = True,
    ):
        """
        Initialize the RAG service.

        Args:
            qdrant_host: Qdrant server host
            qdrant_port: Qdrant server port
            embedding_model: Sentence transformer model name
            cohere_api_key: Cohere API key for reranking (or COHERE_API_KEY env var)
            enable_reranking: Whether to enable Cohere reranking
        """
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
        self.embedder = EmbeddingService(model_name=embedding_model)
        self._initialized = False

        # Initialize Cohere reranker
        self.reranker = None
        self.reranking_enabled = False
        if enable_reranking and COHERE_AVAILABLE:
            api_key = cohere_api_key or os.getenv("COHERE_API_KEY")
            if api_key and "xxxxx" not in api_key:
                try:
                    self.reranker = cohere.Client(api_key)
                    self.reranking_enabled = True
                    logger.info("Cohere reranker initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize Cohere reranker: {e}")

    def initialize(self):
        """Initialize collections and embedding model."""
        if self._initialized:
            return

        logger.info("Initializing RAG service...")

        # Initialize embedder
        self.embedder.initialize()
        dim = self.embedder.get_dimension()

        # Create collections if they don't exist
        existing = {c.name for c in self.client.get_collections().collections}

        for name, _config in self.COLLECTIONS.items():
            if name not in existing:
                self._create_collection(name, dim)
                logger.info(f"Created collection: {name}")
            else:
                logger.debug(f"Collection exists: {name}")

        self._initialized = True
        logger.info("RAG service initialized")

    def _create_collection(self, name: str, embedding_dim: int):
        """Create a Qdrant collection."""
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=embedding_dim,
                distance=Distance.COSINE,
            ),
        )

        # Create payload indexes for filtering
        config = self.COLLECTIONS.get(name, {})
        for field in config.get("metadata_fields", []):
            try:
                # Determine field type
                if field in ["season", "year", "score"]:
                    schema = models.PayloadSchemaType.INTEGER
                elif field in ["published_date", "created_at"]:
                    schema = models.PayloadSchemaType.DATETIME
                elif field in ["quality_score"]:
                    schema = models.PayloadSchemaType.FLOAT
                else:
                    schema = models.PayloadSchemaType.KEYWORD

                self.client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=schema,
                )
            except Exception as e:
                logger.debug(f"Index may exist: {field} - {e}")

    async def _rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 10,
    ) -> list[SearchResult]:
        """
        Rerank results using Cohere.

        Args:
            query: Original search query
            results: List of search results to rerank
            top_k: Number of results to return after reranking

        Returns:
            Reranked list of SearchResult
        """
        if not self.reranking_enabled or not results:
            return results[:top_k]

        try:
            # Prepare documents for reranking
            documents = [r.content for r in results]

            # Call Cohere rerank API
            response = self.reranker.rerank(
                model="rerank-english-v3.0",
                query=query,
                documents=documents,
                top_n=min(top_k, len(documents)),
            )

            # Rebuild results with rerank scores
            reranked = []
            for result in response.results:
                original = results[result.index]
                reranked.append(
                    SearchResult(
                        content=original.content,
                        score=result.relevance_score,  # Use Cohere's relevance score
                        metadata=original.metadata,
                        source=original.source,
                    )
                )

            logger.debug(f"Reranked {len(results)} results to {len(reranked)}")
            return reranked

        except Exception as e:
            logger.warning(f"Reranking failed, using original order: {e}")
            return results[:top_k]

    def _keyword_score(self, query: str, text: str) -> float:
        """
        Simple BM25-like keyword scoring.

        This is a simplified version - for production, use a proper BM25 implementation.
        """
        # Tokenize
        query_tokens = set(re.findall(r"\w+", query.lower()))
        text_tokens = re.findall(r"\w+", text.lower())
        text_token_set = set(text_tokens)

        if not query_tokens or not text_tokens:
            return 0.0

        # Calculate term frequency and document frequency
        matches = query_tokens & text_token_set
        if not matches:
            return 0.0

        # Simple TF-IDF-like score
        tf_sum = sum(text_tokens.count(term) for term in matches)
        score = tf_sum / (len(text_tokens) + 1) * len(matches) / len(query_tokens)

        return min(score, 1.0)

    async def hybrid_search(
        self,
        query: str,
        collection: str,
        limit: int | None = 10,
        filters: dict[str, Any] | None = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        min_score: float = 0.3,
        use_reranking: bool = True,
    ) -> HybridSearchResult:
        """
        Perform hybrid search combining semantic and keyword matching.

        Args:
            query: Search query
            collection: Collection to search
            limit: Maximum results
            filters: Metadata filters
            semantic_weight: Weight for semantic search (0-1)
            keyword_weight: Weight for keyword search (0-1)
            min_score: Minimum combined score threshold
            use_reranking: Whether to apply Cohere reranking (if available)

        Returns:
            HybridSearchResult with ranked results
        """
        if not self._initialized:
            self.initialize()

        # Ensure limit is not None
        if limit is None:
            limit = 10

        # Build Qdrant filter
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if value is not None:
                    if isinstance(value, list):
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchAny(any=value),
                            )
                        )
                    else:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchValue(value=value),
                            )
                        )
            if conditions:
                qdrant_filter = models.Filter(must=conditions)

        # Semantic search
        query_vector = self.embedder.embed(query)

        # Fetch more results for reranking
        fetch_limit = min(limit * 3, 50)

        semantic_results = self.client.query_points(
            collection_name=collection,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=fetch_limit,
            with_payload=True,
        ).points

        # Combine with keyword scores
        results = []
        text_field = self.COLLECTIONS.get(collection, {}).get("text_field", "content")

        for hit in semantic_results:
            content = hit.payload.get(text_field, "")
            semantic_score = hit.score if hit.score is not None else 0.0

            # Calculate keyword score
            keyword_score = self._keyword_score(query, content)

            # Combine scores
            combined_score = (semantic_weight * semantic_score) + (keyword_weight * keyword_score)

            if combined_score >= min_score:
                results.append(
                    SearchResult(
                        content=content,
                        score=combined_score,
                        metadata={k: v for k, v in hit.payload.items() if k != text_field},
                        source=collection,
                    )
                )

        # Sort by combined score
        results.sort(key=lambda x: x.score, reverse=True)

        # Apply Cohere reranking if enabled and available
        if use_reranking and self.reranking_enabled and len(results) > 1:
            results = await self._rerank(query, results, top_k=limit)
        else:
            results = results[:limit]

        return HybridSearchResult(
            results=results,
            query=query,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )

    async def search_race_context(
        self,
        query: str,
        race_id: str | None = None,
        season: int | None = None,
        drivers: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Search for race context from reports.

        Args:
            query: Search query
            race_id: Filter by race
            season: Filter by season
            drivers: Filter by drivers mentioned
            limit: Max results

        Returns:
            List of relevant context documents
        """
        filters = {}
        if race_id:
            filters["race_id"] = race_id
        if season:
            filters["season"] = season
        if drivers:
            filters["drivers"] = drivers

        result = await self.hybrid_search(
            query=query,
            collection="race_reports",
            limit=limit,
            filters=filters if filters else None,
        )

        return [r.to_dict() for r in result.results]

    async def search_regulations(
        self,
        query: str,
        document_type: str | None = None,
        year: int | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Search FIA regulations.

        Args:
            query: Search query
            document_type: "sporting" or "technical"
            year: Regulation year
            limit: Max results

        Returns:
            List of relevant regulation excerpts
        """
        filters = {}
        if document_type:
            filters["document_type"] = document_type
        if year:
            filters["year"] = year

        result = await self.hybrid_search(
            query=query,
            collection="regulations",
            limit=limit,
            filters=filters if filters else None,
        )

        return [r.to_dict() for r in result.results]

    async def search_similar_analyses(
        self,
        query: str,
        query_type: str | None = None,
        limit: int = 3,
    ) -> list[dict]:
        """
        Search for similar past analyses.

        Args:
            query: Current query
            query_type: Type of analysis
            limit: Max results

        Returns:
            List of similar past analyses
        """
        filters = {}
        if query_type:
            filters["query_type"] = query_type

        result = await self.hybrid_search(
            query=query,
            collection="past_analyses",
            limit=limit,
            filters=filters if filters else None,
            semantic_weight=0.9,  # Rely more on semantic for similar queries
            keyword_weight=0.1,
        )

        return [r.to_dict() for r in result.results]

    async def add_document(
        self,
        collection: str,
        content: str,
        metadata: dict[str, Any],
        doc_id: str | None = None,
    ) -> str:
        """
        Add a document to a collection.

        Args:
            collection: Target collection
            content: Document content
            metadata: Document metadata
            doc_id: Optional document ID

        Returns:
            Document ID
        """
        if not self._initialized:
            self.initialize()

        doc_id = doc_id or str(uuid.uuid4())
        vector = self.embedder.embed(content)

        # Get text field name
        text_field = self.COLLECTIONS.get(collection, {}).get("text_field", "content")

        payload = {text_field: content, **metadata}

        self.client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=doc_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

        logger.debug(f"Added document {doc_id} to {collection}")
        return doc_id

    async def add_documents_batch(
        self,
        collection: str,
        documents: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """
        Add multiple documents to a collection.

        Args:
            collection: Target collection
            documents: List of {"content": str, "metadata": dict}
            batch_size: Batch size for embedding and upload

        Returns:
            Number of documents added
        """
        if not self._initialized:
            self.initialize()

        text_field = self.COLLECTIONS.get(collection, {}).get("text_field", "content")
        total_added = 0

        # Process in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            # Extract content for embedding
            contents = [doc.get("content", "") for doc in batch]
            vectors = self.embedder.embed_batch(contents)

            # Create points
            points = []
            for j, doc in enumerate(batch):
                doc_id = doc.get("id", str(uuid.uuid4()))
                payload = {text_field: doc.get("content", ""), **doc.get("metadata", {})}

                points.append(
                    models.PointStruct(
                        id=doc_id,
                        vector=vectors[j],
                        payload=payload,
                    )
                )

            # Upsert batch
            self.client.upsert(collection_name=collection, points=points)
            total_added += len(points)

            logger.info(f"Added batch {i // batch_size + 1}: {len(points)} documents to {collection}")

        return total_added

    async def store_analysis(
        self,
        query: str,
        analysis: str,
        query_type: str,
        drivers: list[str] | None = None,
        race_id: str | None = None,
    ) -> str:
        """
        Store an analysis for future reference.

        Args:
            query: Original user query
            analysis: Generated analysis
            query_type: Type of analysis
            drivers: Related drivers
            race_id: Related race

        Returns:
            Document ID
        """
        metadata = {
            "query": query,
            "query_type": query_type,
            "drivers": drivers or [],
            "race_id": race_id,
            "created_at": datetime.utcnow().isoformat(),
        }

        return await self.add_document(
            collection="past_analyses",
            content=analysis,
            metadata=metadata,
        )

    def get_collection_stats(self) -> dict[str, dict]:
        """Get statistics for all collections."""
        stats = {}
        for name in self.COLLECTIONS:
            try:
                info = self.client.get_collection(name)
                stats[name] = {
                    "points_count": getattr(info, "points_count", 0),
                    "vectors_count": getattr(info, "vectors_count", getattr(info, "points_count", 0)),
                    "status": str(getattr(info, "status", "unknown")),
                }
            except Exception as e:
                stats[name] = {"error": str(e)}
        return stats

    def health_check(self) -> bool:
        """Check if RAG service is healthy."""
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False


# Global RAG service instance
_rag_service: RAGService | None = None


async def get_rag_service(
    qdrant_host: str = "qdrant",
    qdrant_port: int = 6333,
) -> RAGService:
    """Get or create the global RAG service."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService(qdrant_host=qdrant_host, qdrant_port=qdrant_port)
        _rag_service.initialize()
    return _rag_service
