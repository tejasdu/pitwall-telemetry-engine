"""Tests for Pitwall Telemetry Engine API."""

from fastapi.testclient import TestClient

from pitwall_telemetry_engine.api.app import app

client = TestClient(app)


def test_root_endpoint():
    """Assert root endpoint returns 200 and serves the web cockpit HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Pitwall" in response.text or "PITWALL" in response.text


def test_health_endpoint():
    """Assert /health endpoint returns 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pitwall-telemetry-engine"
    assert "version" in data


def test_api_health_endpoint():
    """Assert /api/health endpoint returns 200 and healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pitwall-telemetry-engine"
    assert "version" in data

