"""
Ingestion Orchestrator

Coordinates data extraction and loading across all data stores:
- FastF1 -> TimescaleDB (telemetry, laps, results, weather)
- FastF1 -> Neo4j (knowledge graph)
- Qdrant (vector collections initialization)

Provides CLI interface for running ingestion jobs.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from ingestion.extractors.fastf1_extractor import FastF1Extractor, RaceWeekend
from ingestion.loaders.neo4j_loader import Neo4jLoader
from ingestion.loaders.qdrant_loader import QdrantLoader
from ingestion.loaders.timescale_loader import TimescaleLoader

logger = logging.getLogger(__name__)


@dataclass
class IngestionConfig:
    """Configuration for ingestion jobs."""

    # TimescaleDB (use Docker service name inside container, localhost for external)
    timescale_url: str = "postgresql://f1:f1_password@timescaledb:5432/f1_telemetry"

    # Neo4j (use Docker service name inside container)
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "f1_password"

    # Qdrant (use Docker service name inside container)
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    # FastF1
    fastf1_cache_dir: str = "/tmp/fastf1_cache"

    # Embedding config
    embedding_dim: int = 768  # BGE base default


@dataclass
class IngestionStats:
    """Statistics from an ingestion run."""

    races_processed: int = 0
    races_failed: int = 0
    laps_loaded: int = 0
    telemetry_points_loaded: int = 0
    graph_nodes_created: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    def __str__(self) -> str:
        return (
            f"Ingestion Stats:\n"
            f"  Races: {self.races_processed} processed, {self.races_failed} failed\n"
            f"  Duration: {self.duration_seconds:.1f}s"
        )


class IngestionOrchestrator:
    """Orchestrate F1 data ingestion across all data stores."""

    def __init__(self, config: IngestionConfig | None = None):
        """
        Initialize the orchestrator.

        Args:
            config: Ingestion configuration (uses defaults if not provided)
        """
        self.config = config or IngestionConfig()
        self.extractor = FastF1Extractor(cache_dir=self.config.fastf1_cache_dir)
        self.timescale: TimescaleLoader | None = None
        self.neo4j: Neo4jLoader | None = None
        self.qdrant: QdrantLoader | None = None
        self.stats = IngestionStats()

    async def initialize(self):
        """Initialize all data store connections and schemas."""
        logger.info("Initializing data stores...")

        # Initialize TimescaleDB
        self.timescale = TimescaleLoader(self.config.timescale_url)
        await self.timescale.initialize()
        logger.info("TimescaleDB initialized")

        # Initialize Neo4j
        self.neo4j = Neo4jLoader(
            uri=self.config.neo4j_uri,
            user=self.config.neo4j_user,
            password=self.config.neo4j_password,
        )
        await self.neo4j.initialize()
        logger.info("Neo4j initialized")

        # Initialize Qdrant
        self.qdrant = QdrantLoader(
            host=self.config.qdrant_host,
            port=self.config.qdrant_port,
        )
        self.qdrant.initialize(embedding_dim=self.config.embedding_dim)
        logger.info("Qdrant initialized")

        logger.info("All data stores initialized successfully")

    async def close(self):
        """Close all data store connections."""
        if self.timescale:
            await self.timescale.close()
        if self.neo4j:
            await self.neo4j.close()
        logger.info("All data store connections closed")

    async def ingest_race(
        self,
        year: int,
        round_number: int,
        session_types: list[str] | None = None,
        include_telemetry: bool = True,
    ) -> bool:
        """
        Ingest a single race weekend.

        Args:
            year: Season year
            round_number: Round number in the season
            session_types: Session types to ingest (default: ["R"] for race only)
            include_telemetry: Whether to include telemetry data

        Returns:
            True if successful
        """
        session_types = session_types or ["R"]
        logger.info(f"Ingesting {year} Round {round_number}, sessions: {session_types}")

        success = True
        for session_type in session_types:
            try:
                # Extract data from FastF1
                session_data = self.extractor.extract_session(
                    year=year,
                    round_number=round_number,
                    session_type=session_type,
                    include_telemetry=include_telemetry,
                )

                if session_data is None:
                    logger.warning(
                        f"Failed to extract {year} R{round_number} {session_type}"
                    )
                    success = False
                    continue

                # Load into TimescaleDB
                if self.timescale:
                    ts_success = await self.timescale.load_session(session_data)
                    if not ts_success:
                        logger.warning(
                            f"TimescaleDB load failed for {year} R{round_number} {session_type}"
                        )
                        success = False

                # Load into Neo4j (only for race sessions to build knowledge graph)
                if self.neo4j and session_type == "R":
                    neo_success = await self.neo4j.load_session(session_data)
                    if not neo_success:
                        logger.warning(
                            f"Neo4j load failed for {year} R{round_number} {session_type}"
                        )
                        success = False

                logger.info(
                    f"Completed {year} R{round_number} {session_type}: "
                    f"{session_data.event_name}"
                )

            except Exception as e:
                logger.error(
                    f"Error ingesting {year} R{round_number} {session_type}: {e}"
                )
                success = False

        return success

    async def ingest_season(
        self,
        year: int,
        include_practice: bool = False,
        include_qualifying: bool = True,
        include_telemetry: bool = True,
    ) -> IngestionStats:
        """
        Ingest an entire season.

        Args:
            year: Season year
            include_practice: Include FP1, FP2, FP3 sessions
            include_qualifying: Include Q and sprint qualifying sessions
            include_telemetry: Include telemetry data

        Returns:
            Ingestion statistics
        """
        logger.info(f"Starting ingestion for {year} season")
        self.stats = IngestionStats(start_time=datetime.now())

        # Get all races for the season
        races = self.extractor.get_available_races(start_year=year, end_year=year)
        logger.info(f"Found {len(races)} races for {year}")

        for race in races:
            # Determine which sessions to ingest
            session_types = ["R"]  # Always include race

            if include_qualifying:
                if "Q" in race.sessions:
                    session_types.append("Q")
                if "SQ" in race.sessions:
                    session_types.append("SQ")
                if "SS" in race.sessions:
                    session_types.append("SS")

            if include_practice:
                for fp in ["FP1", "FP2", "FP3"]:
                    if fp in race.sessions:
                        session_types.append(fp)

            # Ingest the race
            success = await self.ingest_race(
                year=race.year,
                round_number=race.round_number,
                session_types=session_types,
                include_telemetry=include_telemetry,
            )

            if success:
                self.stats.races_processed += 1
            else:
                self.stats.races_failed += 1

            logger.info(
                f"Progress: {self.stats.races_processed}/{len(races)} races "
                f"({self.stats.races_failed} failed)"
            )

        self.stats.end_time = datetime.now()
        logger.info(f"Season {year} ingestion complete: {self.stats}")
        return self.stats

    async def ingest_range(
        self,
        start_year: int = 2018,
        end_year: int = 2024,
        include_practice: bool = False,
        include_qualifying: bool = True,
        include_telemetry: bool = True,
    ) -> IngestionStats:
        """
        Ingest multiple seasons.

        Args:
            start_year: First season to ingest
            end_year: Last season to ingest
            include_practice: Include practice sessions
            include_qualifying: Include qualifying sessions
            include_telemetry: Include telemetry data

        Returns:
            Combined ingestion statistics
        """
        logger.info(f"Starting ingestion for {start_year}-{end_year}")
        combined_stats = IngestionStats(start_time=datetime.now())

        for year in range(start_year, end_year + 1):
            season_stats = await self.ingest_season(
                year=year,
                include_practice=include_practice,
                include_qualifying=include_qualifying,
                include_telemetry=include_telemetry,
            )
            combined_stats.races_processed += season_stats.races_processed
            combined_stats.races_failed += season_stats.races_failed

        combined_stats.end_time = datetime.now()
        logger.info(f"Full ingestion complete: {combined_stats}")
        return combined_stats

    async def health_check(self) -> dict[str, bool]:
        """Check health of all data stores."""
        health = {
            "timescale": False,
            "neo4j": False,
            "qdrant": False,
        }

        if self.timescale and self.timescale.pool:
            try:
                async with self.timescale.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                health["timescale"] = True
            except Exception:
                pass

        if self.neo4j:
            try:
                await self.neo4j.get_driver_count()
                health["neo4j"] = True
            except Exception:
                pass

        if self.qdrant:
            health["qdrant"] = self.qdrant.health_check()

        return health

    async def get_stats(self) -> dict:
        """Get current data store statistics."""
        stats = {}

        if self.timescale:
            stats["timescale"] = {
                "sessions": await self.timescale.get_session_count(),
                "laps": await self.timescale.get_lap_count(),
            }

        if self.neo4j:
            stats["neo4j"] = {
                "drivers": await self.neo4j.get_driver_count(),
                "races": await self.neo4j.get_race_count(),
            }

        if self.qdrant:
            stats["qdrant"] = {
                "collections": self.qdrant.get_all_collections_info(),
            }

        return stats


async def run_ingestion(
    years: list[int] | None = None,
    races: list[tuple[int, int]] | None = None,
    include_practice: bool = False,
    include_qualifying: bool = True,
    include_telemetry: bool = True,
    config: IngestionConfig | None = None,
):
    """
    Run ingestion job.

    Args:
        years: List of years to ingest (e.g., [2023, 2024])
        races: List of specific races as (year, round) tuples
        include_practice: Include practice sessions
        include_qualifying: Include qualifying sessions
        include_telemetry: Include telemetry data
        config: Custom configuration
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    orchestrator = IngestionOrchestrator(config)

    try:
        await orchestrator.initialize()

        # Check health
        health = await orchestrator.health_check()
        logger.info(f"Data store health: {health}")

        if not all(health.values()):
            unhealthy = [k for k, v in health.items() if not v]
            logger.error(f"Unhealthy data stores: {unhealthy}")
            return

        # Run ingestion
        if races:
            # Ingest specific races
            for year, round_num in races:
                await orchestrator.ingest_race(
                    year=year,
                    round_number=round_num,
                    include_telemetry=include_telemetry,
                )
        elif years:
            # Ingest specific years
            for year in years:
                await orchestrator.ingest_season(
                    year=year,
                    include_practice=include_practice,
                    include_qualifying=include_qualifying,
                    include_telemetry=include_telemetry,
                )
        else:
            # Default: ingest all available data
            await orchestrator.ingest_range(
                start_year=2018,
                end_year=2024,
                include_practice=include_practice,
                include_qualifying=include_qualifying,
                include_telemetry=include_telemetry,
            )

        # Print final stats
        stats = await orchestrator.get_stats()
        logger.info(f"Final data store stats: {stats}")

    finally:
        await orchestrator.close()


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F1 Data Ingestion")
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        help="Specific years to ingest (e.g., 2023 2024)",
    )
    parser.add_argument(
        "--race",
        type=str,
        help="Specific race to ingest (format: YEAR:ROUND, e.g., 2024:1)",
    )
    parser.add_argument(
        "--practice",
        action="store_true",
        help="Include practice sessions",
    )
    parser.add_argument(
        "--no-qualifying",
        action="store_true",
        help="Exclude qualifying sessions",
    )
    parser.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Exclude telemetry data (faster, smaller)",
    )

    args = parser.parse_args()

    # Parse race argument if provided
    races = None
    if args.race:
        year, round_num = args.race.split(":")
        races = [(int(year), int(round_num))]

    asyncio.run(
        run_ingestion(
            years=args.years,
            races=races,
            include_practice=args.practice,
            include_qualifying=not args.no_qualifying,
            include_telemetry=not args.no_telemetry,
        )
    )
