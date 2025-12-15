"""
Ergast API Integration

Fetches historical F1 data from the Ergast API (1950-present).
This provides supplementary data for seasons not covered by FastF1.

API: https://ergast.com/mrd/
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

ERGAST_BASE_URL = "https://ergast.com/api/f1"


@dataclass
class DriverInfo:
    """Driver information from Ergast."""

    driver_id: str
    code: str | None
    permanent_number: str | None
    given_name: str
    family_name: str
    date_of_birth: str | None
    nationality: str
    url: str | None


@dataclass
class ConstructorInfo:
    """Constructor/team information from Ergast."""

    constructor_id: str
    name: str
    nationality: str
    url: str | None


@dataclass
class RaceResult:
    """Race result from Ergast."""

    season: int
    round: int
    race_name: str
    circuit_name: str
    date: str
    driver_id: str
    driver_name: str
    constructor: str
    position: int | None
    points: float
    status: str
    grid: int | None
    laps: int | None
    fastest_lap_time: str | None
    fastest_lap_rank: int | None


class ErgastClient:
    """
    Client for the Ergast F1 API.

    Provides access to historical F1 data back to 1950.
    """

    def __init__(self, base_url: str = ERGAST_BASE_URL):
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _fetch(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Fetch data from Ergast API."""
        client = await self._get_client()
        url = f"{self.base_url}/{endpoint}.json"

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Ergast API error: {e}")
            return None

    async def get_season_races(self, year: int) -> list[dict]:
        """Get all races for a season."""
        data = await self._fetch(f"{year}")
        if data and "MRData" in data:
            return data["MRData"]["RaceTable"]["Races"]
        return []

    async def get_race_results(self, year: int, round_num: int) -> list[RaceResult]:
        """Get results for a specific race."""
        data = await self._fetch(f"{year}/{round_num}/results")
        if not data or "MRData" not in data:
            return []

        results = []
        races = data["MRData"]["RaceTable"]["Races"]

        if not races:
            return []

        race = races[0]
        for result in race.get("Results", []):
            driver = result["Driver"]
            constructor = result["Constructor"]

            fastest_lap = result.get("FastestLap", {})

            results.append(
                RaceResult(
                    season=int(race["season"]),
                    round=int(race["round"]),
                    race_name=race["raceName"],
                    circuit_name=race["Circuit"]["circuitName"],
                    date=race["date"],
                    driver_id=driver["driverId"],
                    driver_name=f"{driver['givenName']} {driver['familyName']}",
                    constructor=constructor["name"],
                    position=int(result["position"]) if result.get("position") else None,
                    points=float(result.get("points", 0)),
                    status=result.get("status", ""),
                    grid=int(result["grid"]) if result.get("grid") else None,
                    laps=int(result["laps"]) if result.get("laps") else None,
                    fastest_lap_time=fastest_lap.get("Time", {}).get("time"),
                    fastest_lap_rank=int(fastest_lap["rank"]) if fastest_lap.get("rank") else None,
                )
            )

        return results

    async def get_driver_standings(self, year: int) -> list[dict]:
        """Get driver standings for a season."""
        data = await self._fetch(f"{year}/driverStandings")
        if data and "MRData" in data:
            standings_table = data["MRData"]["StandingsTable"]
            if standings_table.get("StandingsLists"):
                return standings_table["StandingsLists"][0].get("DriverStandings", [])
        return []

    async def get_constructor_standings(self, year: int) -> list[dict]:
        """Get constructor standings for a season."""
        data = await self._fetch(f"{year}/constructorStandings")
        if data and "MRData" in data:
            standings_table = data["MRData"]["StandingsTable"]
            if standings_table.get("StandingsLists"):
                return standings_table["StandingsLists"][0].get("ConstructorStandings", [])
        return []

    async def get_all_drivers(self, limit: int = 1000) -> list[DriverInfo]:
        """Get all drivers in F1 history."""
        data = await self._fetch("drivers", params={"limit": limit})
        if not data or "MRData" not in data:
            return []

        drivers = []
        for d in data["MRData"]["DriverTable"]["Drivers"]:
            drivers.append(
                DriverInfo(
                    driver_id=d["driverId"],
                    code=d.get("code"),
                    permanent_number=d.get("permanentNumber"),
                    given_name=d["givenName"],
                    family_name=d["familyName"],
                    date_of_birth=d.get("dateOfBirth"),
                    nationality=d["nationality"],
                    url=d.get("url"),
                )
            )
        return drivers

    async def get_all_constructors(self, limit: int = 500) -> list[ConstructorInfo]:
        """Get all constructors in F1 history."""
        data = await self._fetch("constructors", params={"limit": limit})
        if not data or "MRData" not in data:
            return []

        constructors = []
        for c in data["MRData"]["ConstructorTable"]["Constructors"]:
            constructors.append(
                ConstructorInfo(
                    constructor_id=c["constructorId"],
                    name=c["name"],
                    nationality=c["nationality"],
                    url=c.get("url"),
                )
            )
        return constructors


class ErgastIngester:
    """
    Ingests historical F1 data from Ergast into the RAG system.

    Creates searchable documents for:
    - Season summaries
    - Race reports
    - Driver profiles
    - Team histories
    """

    def __init__(self, rag_service=None):
        self.client = ErgastClient()
        self.rag_service = rag_service

    async def _get_rag_service(self):
        if self.rag_service is None:
            from agent.rag.service import get_rag_service

            self.rag_service = await get_rag_service()
        return self.rag_service

    async def close(self):
        await self.client.close()

    def _format_race_report(self, race_results: list[RaceResult]) -> str:
        """Format race results as a narrative report."""
        if not race_results:
            return ""

        first = race_results[0]
        lines = [
            f"# {first.season} {first.race_name}",
            f"Circuit: {first.circuit_name}",
            f"Date: {first.date}",
            "",
            "## Race Results",
        ]

        # Top 10
        for r in race_results[:10]:
            pos_str = f"P{r.position}" if r.position else "DNF"
            fl_str = f" (FL: {r.fastest_lap_time})" if r.fastest_lap_time and r.fastest_lap_rank == 1 else ""
            lines.append(f"{pos_str}: {r.driver_name} ({r.constructor}) - {r.points} pts{fl_str}")

        # DNFs
        dnfs = [r for r in race_results if r.status and "Finished" not in r.status]
        if dnfs:
            lines.append("")
            lines.append(f"Retirements: {len(dnfs)} ({', '.join(r.driver_name.split()[-1] for r in dnfs[:5])})")

        return "\n".join(lines)

    def _format_season_summary(
        self,
        year: int,
        driver_standings: list[dict],
        constructor_standings: list[dict],
    ) -> str:
        """Format season summary as narrative."""
        lines = [
            f"# {year} Formula 1 World Championship Summary",
            "",
        ]

        # Driver championship
        if driver_standings:
            lines.append("## Drivers' Championship")
            for i, ds in enumerate(driver_standings[:10], 1):
                driver = ds["Driver"]
                name = f"{driver['givenName']} {driver['familyName']}"
                constructor = ds["Constructors"][0]["name"] if ds.get("Constructors") else "Unknown"
                points = ds["points"]
                wins = ds["wins"]
                lines.append(f"{i}. {name} ({constructor}) - {points} pts, {wins} wins")

        lines.append("")

        # Constructor championship
        if constructor_standings:
            lines.append("## Constructors' Championship")
            for i, cs in enumerate(constructor_standings[:10], 1):
                name = cs["Constructor"]["name"]
                points = cs["points"]
                wins = cs["wins"]
                lines.append(f"{i}. {name} - {points} pts, {wins} wins")

        return "\n".join(lines)

    async def ingest_season(self, year: int) -> int:
        """
        Ingest all data for a season.

        Args:
            year: Season year

        Returns:
            Number of documents ingested
        """
        rag = await self._get_rag_service()
        documents = []

        logger.info(f"Fetching Ergast data for {year}...")

        # Get races
        races = await self.client.get_season_races(year)
        logger.info(f"Found {len(races)} races for {year}")

        # Ingest each race
        for race in races:
            round_num = int(race["round"])
            results = await self.client.get_race_results(year, round_num)

            if results:
                report = self._format_race_report(results)
                if report:
                    documents.append(
                        {
                            "content": report,
                            "metadata": {
                                "source": "ergast",
                                "race_id": f"{year}_{round_num}_R",
                                "season": year,
                                "event_name": race["raceName"],
                                "circuit": race["Circuit"]["circuitName"],
                                "date": race["date"],
                            },
                        }
                    )

            # Rate limit
            await asyncio.sleep(0.5)

        # Get season summary
        driver_standings = await self.client.get_driver_standings(year)
        constructor_standings = await self.client.get_constructor_standings(year)

        if driver_standings or constructor_standings:
            summary = self._format_season_summary(year, driver_standings, constructor_standings)
            documents.append(
                {
                    "content": summary,
                    "metadata": {
                        "source": "ergast",
                        "season": year,
                        "document_type": "season_summary",
                    },
                }
            )

        # Ingest to RAG
        if documents:
            count = await rag.add_documents_batch(
                collection="race_reports",
                documents=documents,
            )
            logger.info(f"Ingested {count} documents for {year}")
            return count

        return 0

    async def ingest_range(self, start_year: int, end_year: int) -> int:
        """
        Ingest data for a range of seasons.

        Args:
            start_year: First season
            end_year: Last season

        Returns:
            Total documents ingested
        """
        total = 0
        for year in range(start_year, end_year + 1):
            count = await self.ingest_season(year)
            total += count
            logger.info(f"Progress: {year} complete, {total} total documents")

        return total

    async def ingest_historical(self, decades: list[int] | None = None) -> int:
        """
        Ingest historical data by decade.

        Args:
            decades: List of decade start years (e.g., [1950, 1960, 1970])
                     If None, ingests notable seasons only

        Returns:
            Total documents ingested
        """
        # Notable seasons for F1 history
        notable_seasons = [
            1950,  # First championship
            1958,  # First constructors' championship
            1976,  # Hunt vs Lauda
            1984,  # Prost vs Lauda
            1988,  # Senna vs Prost begins
            1994,  # Senna's death, Schumacher's first title
            2000,  # Schumacher/Ferrari dominance begins
            2008,  # Hamilton's first title
            2010,  # Close four-way fight
            2016,  # Rosberg vs Hamilton
            2021,  # Verstappen vs Hamilton
        ]

        seasons_to_ingest = notable_seasons if decades is None else []

        if decades:
            for decade in decades:
                seasons_to_ingest.extend(range(decade, decade + 10))

        total = 0
        for year in sorted(set(seasons_to_ingest)):
            try:
                count = await self.ingest_season(year)
                total += count
            except Exception as e:
                logger.error(f"Failed to ingest {year}: {e}")

        return total


async def ingest_ergast_data(
    rag_service=None,
    years: list[int] | None = None,
    historical: bool = False,
) -> int:
    """
    Convenience function to ingest Ergast data.

    Args:
        rag_service: Optional RAG service instance
        years: Specific years to ingest
        historical: If True, ingest notable historical seasons

    Returns:
        Number of documents ingested
    """
    ingester = ErgastIngester(rag_service)

    try:
        if years:
            total = 0
            for year in years:
                total += await ingester.ingest_season(year)
            return total
        elif historical:
            return await ingester.ingest_historical()
        else:
            # Default: recent seasons not covered by FastF1
            return await ingester.ingest_range(2018, 2020)
    finally:
        await ingester.close()
