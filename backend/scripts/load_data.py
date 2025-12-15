#!/usr/bin/env python3
"""
F1 Data Loading Script

Loads F1 data from FastF1 into the databases.
Run inside the backend container: docker compose exec backend python scripts/load_data.py

Monitor progress: tail -f /tmp/f1_ingestion.log
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.orchestrator import IngestionOrchestrator, IngestionConfig

# Log file path
LOG_FILE = "/tmp/f1_ingestion.log"


async def main():
    """Main entry point for data loading."""
    # Set up logging to both file and console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger(__name__)

    # Configuration for Docker environment
    config = IngestionConfig(
        timescale_url="postgresql://f1:f1_password@timescaledb:5432/f1_telemetry",
        neo4j_uri="bolt://neo4j:7687",
        neo4j_user="neo4j",
        neo4j_password="f1_password",
        qdrant_host="qdrant",
        qdrant_port=6333,
        fastf1_cache_dir="/tmp/fastf1_cache",
    )

    orchestrator = IngestionOrchestrator(config)

    try:
        logger.info("=" * 60)
        logger.info("F1 Data Ingestion - Full Load (2021-2024)")
        logger.info("=" * 60)
        logger.info("")
        logger.info("This will load:")
        logger.info("  - 2021: 22 races with full telemetry")
        logger.info("  - 2022: 22 races with full telemetry")
        logger.info("  - 2023: 22 races with full telemetry")
        logger.info("  - 2024: 24 races with full telemetry")
        logger.info("")
        logger.info("Estimated time: 4-6 hours")
        logger.info("Estimated storage: ~35-40 GB")
        logger.info("")
        logger.info("=" * 60)

        # Initialize connections
        logger.info("Initializing data stores...")
        await orchestrator.initialize()

        # Health check
        health = await orchestrator.health_check()
        logger.info(f"Data store health: {health}")

        if not all(health.values()):
            unhealthy = [k for k, v in health.items() if not v]
            logger.error(f"Cannot proceed - unhealthy stores: {unhealthy}")
            return

        # Get current stats
        stats_before = await orchestrator.get_stats()
        logger.info(f"Current data: {stats_before}")

        # Load data year by year
        years = [2021, 2022, 2023, 2024]

        for year in years:
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"LOADING {year} SEASON")
            logger.info("=" * 60)

            await orchestrator.ingest_season(
                year=year,
                include_practice=False,  # Skip practice to save time/space
                include_qualifying=True,  # Include quali for strategy analysis
                include_telemetry=True,   # Full telemetry
            )

            # Progress stats
            stats = await orchestrator.get_stats()
            logger.info(f"Progress after {year}: {stats}")

        # Final stats
        stats_after = await orchestrator.get_stats()
        logger.info("")
        logger.info("=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Final data: {stats_after}")

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error during ingestion: {e}", exc_info=True)
    finally:
        await orchestrator.close()
        logger.info("Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
