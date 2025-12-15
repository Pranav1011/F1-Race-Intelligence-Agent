"""
Content Ingestion Module

Handles ingestion of text content into the RAG system:
- FIA regulations (sporting and technical)
- Race reports and articles
- Historical data from Ergast API
"""

from ingestion.content.regulations import RegulationsIngester
from ingestion.content.ergast import ErgastIngester

__all__ = ["RegulationsIngester", "ErgastIngester"]
