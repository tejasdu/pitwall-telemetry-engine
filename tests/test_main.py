"""Tests for Pitwall Telemetry Engine API."""

from fastapi.testclient import TestClient

from pitwall_telemetry_engine.api.app import app

client = TestClient(app)


def test_root_endpoint():
    """Assert root endpoint returns 200 and expected payload."""
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "online"
    assert "engine" in payload
    assert payload.get("docs_url") == "/docs"
