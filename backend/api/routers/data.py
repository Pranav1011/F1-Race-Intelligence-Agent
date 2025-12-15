"""
Data router - Provides access to F1 data.
"""

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/races")
async def list_races(
    year: int | None = Query(None, description="Filter by year"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List available races.

    Returns races with basic metadata (year, round, name, circuit).
    """
    # TODO: Query from TimescaleDB/Neo4j
    return {
        "races": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "message": "Data not yet loaded. Run 'make ingest' to load F1 data.",
    }


@router.get("/drivers")
async def list_drivers(
    year: int | None = Query(None, description="Filter by year"),
    team: str | None = Query(None, description="Filter by team"),
):
    """
    List drivers.

    Returns drivers with team associations.
    """
    # TODO: Query from Neo4j
    return {
        "drivers": [],
        "total": 0,
        "message": "Data not yet loaded. Run 'make ingest' to load F1 data.",
    }


@router.get("/teams")
async def list_teams(
    year: int | None = Query(None, description="Filter by year"),
):
    """
    List teams/constructors.
    """
    # TODO: Query from Neo4j
    return {
        "teams": [],
        "total": 0,
        "message": "Data not yet loaded. Run 'make ingest' to load F1 data.",
    }


@router.get("/standings/drivers")
async def driver_standings(
    year: int = Query(..., description="Championship year"),
    after_round: int | None = Query(None, description="Standings after specific round"),
):
    """
    Get driver championship standings.
    """
    # TODO: Query from Neo4j
    return {
        "year": year,
        "standings": [],
        "message": "Data not yet loaded. Run 'make ingest' to load F1 data.",
    }


@router.get("/standings/constructors")
async def constructor_standings(
    year: int = Query(..., description="Championship year"),
    after_round: int | None = Query(None, description="Standings after specific round"),
):
    """
    Get constructor championship standings.
    """
    # TODO: Query from Neo4j
    return {
        "year": year,
        "standings": [],
        "message": "Data not yet loaded. Run 'make ingest' to load F1 data.",
    }
