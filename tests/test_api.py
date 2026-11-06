"""Tests for Pitwall Telemetry Engine API."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pitwall_telemetry_engine.api import websocket_manager
from pitwall_telemetry_engine.api.app import app

client = TestClient(app)


def test_root_endpoint():
    """Assert root endpoint returns 200 and serves the web cockpit HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Pitwall" in response.text or "PITWALL" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_browser_revalidates_static_scripts():
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    conditional = client.get(
        "/static/js/app.js", headers={"If-None-Match": response.headers["etag"]}
    )
    assert conditional.status_code == 304


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


@pytest.mark.anyio
async def test_switch_session_replaces_the_running_stream(monkeypatch):
    frames = asyncio.Queue()

    class Replay:
        def __init__(self, session_key, fps):
            self.session_key = session_key
            self.fps = fps

        async def stream_frames(self, **kwargs):
            yield self.session_key
            await asyncio.Event().wait()

    async def load_session(session_key):
        return int(session_key)

    monkeypatch.setattr(websocket_manager.session_cache, "get", load_session)
    monkeypatch.setattr(websocket_manager, "TimelineReplayer", Replay)
    manager = websocket_manager.ConnectionManager()
    websocket = AsyncMock()
    websocket.send_json.side_effect = frames.put

    await manager.connect(websocket, session_key=1)
    try:
        assert await asyncio.wait_for(frames.get(), timeout=1) == 1
        await manager.handle_client_message(
            websocket, {"action": "switch_session", "session_key": "2"}
        )
        assert await asyncio.wait_for(frames.get(), timeout=1) == 2
    finally:
        await manager.disconnect(websocket)


@pytest.mark.parametrize(
    ("status_code", "message"),
    [(429, "rate limiting"), (401, "denied access"), (403, "denied access")],
)
def test_upstream_access_failure_reports_launch_error(monkeypatch, status_code, message):
    request = httpx.Request("GET", "https://api.openf1.org/v1/car_data")
    response = httpx.Response(status_code, request=request)
    monkeypatch.setattr(
        websocket_manager.session_cache,
        "get",
        AsyncMock(
            side_effect=httpx.HTTPStatusError("Download failed", request=request, response=response)
        ),
    )

    with client.websocket_connect("/api/ws/telemetry?session_key=42") as socket:
        error = socket.receive_json()
        assert error["type"] == "error"
        assert message in error["message"]
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4004
