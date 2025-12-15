"""
Embedding Service for RAG.

Provides text embeddings using sentence-transformers (BGE model).
Supports caching embeddings for efficiency.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings."""

    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5", cache_size: int = 10000):
        """
        Initialize the embedding service.

        Args:
            model_name: Name of the sentence-transformer model
            cache_size: Maximum number of embeddings to cache
        """
        self.model_name = model_name
        self.model = None
        self.dimension = 768  # BGE base default
        self._cache: dict[str, list[float]] = {}
        self._cache_size = cache_size
        self._initialized = False

    def initialize(self):
        """Load the embedding model."""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            self.dimension = self.model.get_sentence_embedding_dimension()
            self._initialized = True
            logger.info(f"Embedding model loaded (dim={self.dimension})")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode()).hexdigest()

    def embed(self, text: str) -> list[float]:
        """
        Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if not self._initialized:
            self.initialize()

        # Check cache
        cache_key = self._get_cache_key(text)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Generate embedding
        embedding = self.model.encode(text, normalize_embeddings=True).tolist()

        # Cache (with size limit)
        if len(self._cache) >= self._cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[cache_key] = embedding

        return embedding

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        Embed multiple texts efficiently.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for embedding

        Returns:
            List of embedding vectors
        """
        if not self._initialized:
            self.initialize()

        # Check which texts are cached
        uncached_indices = []
        uncached_texts = []
        results = [None] * len(texts)

        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                results[i] = self._cache[cache_key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Embed uncached texts
        if uncached_texts:
            embeddings = self.model.encode(
                uncached_texts,
                normalize_embeddings=True,
                batch_size=batch_size,
                show_progress_bar=len(uncached_texts) > 100,
            )

            for i, (idx, text) in enumerate(zip(uncached_indices, uncached_texts, strict=True)):
                embedding = embeddings[i].tolist()
                results[idx] = embedding

                # Cache
                cache_key = self._get_cache_key(text)
                if len(self._cache) < self._cache_size:
                    self._cache[cache_key] = embedding

        return results

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.dimension

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")


# Global embedding service instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
        _embedding_service.initialize()
    return _embedding_service
