"""
RAG (Retrieval Augmented Generation) module for F1 Race Intelligence Agent.

Provides hybrid search (BM25 + semantic) over:
- Race reports and articles
- FIA regulations
- Past analyses
"""

from agent.rag.embeddings import EmbeddingService
from agent.rag.service import RAGService

__all__ = ["EmbeddingService", "RAGService"]
