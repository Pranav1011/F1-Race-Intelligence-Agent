#!/usr/bin/env python3
"""
Reload Missing Race Data

Reloads lap data for races that have sessions but 0 laps.
Run inside the backend container: docker compose exec backend python scripts/reload_missing_races.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import fastf1
import asyncpg

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def get_missing_races(pool: asyncpg.Pool) -> list[dict]:
    """Get races with sessions but no lap data."""
    query = """
        SELECT
            s.year,
            s.event_name,
            s.session_type,
            s.session_id,
            s.round_number
        FROM sessions s
        LEFT JOIN lap_times lt ON s.session_id = lt.session_id
        WHERE s.session_type = 'R'
        GROUP BY s.year, s.event_name, s.session_type, s.session_id, s.round_number
        HAVING COUNT(lt.lap_number) = 0
        ORDER BY s.year DESC, s.round_number;
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]


async def load_lap_data(
    pool: asyncpg.Pool,
    year: int,
    round_number: int,
    event_name: str,
    session_id: str,
) -> int:
    """Load lap data for a specific race from FastF1."""
    logger.info(f"Loading {year} {event_name} R{round_number}...")

    try:
        # Get session from FastF1
        session = fastf1.get_session(year, round_number, 'R')
        session.load(telemetry=False, weather=False, messages=False)

        laps = session.laps
        if laps is None or len(laps) == 0:
            logger.warning(f"No laps available for {event_name}")
            return 0

        logger.info(f"Found {len(laps)} laps for {event_name}")

        # Helper to safely convert to int, handling NaN
        def safe_int(value):
            if value is None:
                return None
            try:
                import math
                if isinstance(value, float) and math.isnan(value):
                    return None
                return int(value)
            except (ValueError, TypeError):
                return None

        # Helper to safely get timedelta seconds
        def safe_seconds(value):
            if value is None:
                return None
            try:
                import math
                if isinstance(value, float) and math.isnan(value):
                    return None
                if hasattr(value, "total_seconds"):
                    return value.total_seconds()
                return float(value)
            except (ValueError, TypeError):
                return None

        # Prepare lap data for insertion
        records = []
        for _, lap in laps.iterrows():
            driver_num = safe_int(lap.get("DriverNumber"))
            record = {
                "session_id": session_id,
                "driver_id": str(lap.get("Driver", "")),
                "driver_number": str(driver_num) if driver_num is not None else None,  # TEXT field
                "team": str(lap.get("Team", "")),
                "lap_number": safe_int(lap.get("LapNumber")),
                "lap_time_seconds": safe_seconds(lap.get("LapTime")),
                "sector_1_seconds": safe_seconds(lap.get("Sector1Time")),
                "sector_2_seconds": safe_seconds(lap.get("Sector2Time")),
                "sector_3_seconds": safe_seconds(lap.get("Sector3Time")),
                "compound": str(lap.get("Compound", "")),
                "tyre_life": safe_int(lap.get("TyreLife")),
                "stint": safe_int(lap.get("Stint")),
                "is_personal_best": bool(lap.get("IsPersonalBest", False)) if lap.get("IsPersonalBest") is not None else False,
                "position": safe_int(lap.get("Position")),
            }
            # Skip laps without essential data
            if record["driver_id"] and record["lap_number"]:
                records.append(record)

        # Insert into database
        insert_query = """
            INSERT INTO lap_times (
                session_id, driver_id, driver_number, team, lap_number,
                lap_time_seconds, sector_1_seconds, sector_2_seconds, sector_3_seconds,
                compound, tire_life, stint, is_personal_best, position
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
            )
            ON CONFLICT (session_id, driver_id, lap_number) DO NOTHING;
        """

        async with pool.acquire() as conn:
            inserted = 0
            for record in records:
                try:
                    result = await conn.execute(
                        insert_query,
                        record["session_id"],
                        record["driver_id"],
                        record["driver_number"],
                        record["team"],
                        record["lap_number"],
                        record["lap_time_seconds"],
                        record["sector_1_seconds"],
                        record["sector_2_seconds"],
                        record["sector_3_seconds"],
                        record["compound"],
                        record["tyre_life"],
                        record["stint"],
                        record["is_personal_best"],
                        record["position"],
                    )
                    # Check if insert was successful (not a conflict)
                    if "INSERT 0 1" in result:
                        inserted += 1
                except Exception as e:
                    logger.warning(f"Insert error for lap: {e}")

        logger.info(f"Inserted {inserted} laps for {event_name}")
        return inserted

    except Exception as e:
        logger.error(f"Failed to load {event_name}: {e}")
        return 0


async def main():
    """Main entry point."""
    # Initialize FastF1 cache
    cache_dir = "/tmp/fastf1_cache"
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

    # Connect to database
    db_url = os.getenv(
        "TIMESCALE_URL",
        "postgresql://f1:f1_password@timescaledb:5432/f1_telemetry"
    )

    logger.info("Connecting to database...")
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)

    try:
        # Get missing races
        missing = await get_missing_races(pool)
        logger.info(f"Found {len(missing)} races with missing lap data")

        if not missing:
            logger.info("All races have lap data!")
            return

        # Display missing races
        print("\nMissing races:")
        print("-" * 60)
        for race in missing:
            print(f"  {race['year']} R{race['round_number']}: {race['event_name']}")
        print()

        # Load each missing race
        total_laps = 0
        loaded_races = 0

        for race in missing:
            laps = await load_lap_data(
                pool=pool,
                year=race["year"],
                round_number=race["round_number"],
                event_name=race["event_name"],
                session_id=race["session_id"],
            )
            if laps > 0:
                total_laps += laps
                loaded_races += 1

            # Small delay to be nice to the API
            await asyncio.sleep(1)

        # Refresh materialized views
        logger.info("Refreshing materialized views...")
        async with pool.acquire() as conn:
            await conn.execute("REFRESH MATERIALIZED VIEW mv_head_to_head;")
            logger.info("Head-to-head view refreshed")

        # Summary
        print("\n" + "=" * 60)
        print("RELOAD COMPLETE")
        print("=" * 60)
        print(f"  Races loaded: {loaded_races}/{len(missing)}")
        print(f"  Total laps: {total_laps}")
        print()

    finally:
        await pool.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
