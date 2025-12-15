"""
Pytest configuration and fixtures.
"""

import sys
from pathlib import Path

# Add the backend directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from api.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.info = AsyncMock(return_value={"used_memory_human": "1M"})
    mock.dbsize = AsyncMock(return_value=100)
    mock.scan_iter = AsyncMock(return_value=iter([]))
    return mock


@pytest.fixture
def mock_db_pool():
    """Create a mock database connection pool."""
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn)))
    return mock_pool


@pytest.fixture
def sample_lap_data():
    """Sample lap time data for testing."""
    return [
        {
            "lap_number": 1,
            "lap_time_seconds": 95.234,
            "compound": "MEDIUM",
            "tire_life": 1,
            "stint": 1,
            "position": 3,
        },
        {
            "lap_number": 2,
            "lap_time_seconds": 93.456,
            "compound": "MEDIUM",
            "tire_life": 2,
            "stint": 1,
            "position": 3,
        },
        {
            "lap_number": 3,
            "lap_time_seconds": 93.789,
            "compound": "MEDIUM",
            "tire_life": 3,
            "stint": 1,
            "position": 2,
        },
    ]


@pytest.fixture
def sample_stint_data():
    """Sample stint summary data for testing."""
    return [
        {
            "driver": "VER",
            "stint": 1,
            "compound": "MEDIUM",
            "startLap": 1,
            "endLap": 20,
            "totalLaps": 20,
            "avgPace": 93.5,
        },
        {
            "driver": "VER",
            "stint": 2,
            "compound": "HARD",
            "startLap": 21,
            "endLap": 57,
            "totalLaps": 37,
            "avgPace": 94.2,
        },
    ]
