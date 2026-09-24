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
