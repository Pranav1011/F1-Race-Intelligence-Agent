"""
F1 Data Ingestion Package

Extracts F1 data from FastF1 and loads into:
- TimescaleDB (telemetry, laps, weather)
- Neo4j (knowledge graph)
- Qdrant (vector collections)
"""

from ingestion.orchestrator import (
    IngestionConfig,
    IngestionOrchestrator,
    IngestionStats,
    run_ingestion,
)

__all__ = [
    "IngestionConfig",
    "IngestionOrchestrator",
    "IngestionStats",
    "run_ingestion",
]
