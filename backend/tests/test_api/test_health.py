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
    """Test health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "checks" in data
