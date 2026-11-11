"""
Tests for API health endpoints.
"""


def test_root(client):
    """Test root endpoint returns expected response."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "F1 Race Intelligence Agent"
    assert data["status"] == "running"


def test_health_check(client):
    """The health endpoint answers and reports each backing service.

    "degraded" is the correct answer when the databases are not running (as in
    CI); "healthy" when they are.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in {"healthy", "degraded"}
    assert "checks" in data
