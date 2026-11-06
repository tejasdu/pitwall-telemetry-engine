import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from pitwall_telemetry_engine.ingestion import cache_manager, openf1_client


def test_force_refreshes_existing_cache_and_preserves_it_on_fetch_error(tmp_path, monkeypatch):
    monkeypatch.setattr(openf1_client, "CACHE_DIR", tmp_path)
    cache_file = tmp_path / "42" / "intervals.json"
    cache_file.parent.mkdir()
    cache_file.write_text("invalid JSON", encoding="utf-8")
    row = {
        "date": "2024-03-02T15:00:00Z",
        "driver_number": 1,
        "meeting_key": 10,
        "session_key": 42,
        "gap_to_leader": 0.0,
    }
    request = httpx.Request("GET", f"{openf1_client.BASE_URL}/intervals?session_key=42")
    fetch = Mock(
        side_effect=[
            httpx.Response(200, json=[row], request=request),
            httpx.Response(503, request=request),
        ]
    )
    monkeypatch.setattr(openf1_client.httpx, "get", fetch)

    assert openf1_client.get_intervals(42, force=True)[0].gap_to_leader == 0.0
    assert openf1_client.get_intervals(42)[0].driver_number == 1
    assert fetch.call_count == 1
    with pytest.raises(httpx.HTTPStatusError):
        openf1_client.get_intervals(42, force=True)
    assert json.loads(cache_file.read_text(encoding="utf-8"))[0]["driver_number"] == 1
    assert list(cache_file.parent.iterdir()) == [cache_file]


def test_calendar_refresh_updates_picker_and_preserves_snapshot_on_401(tmp_path, monkeypatch):
    monkeypatch.setattr(openf1_client, "CACHE_DIR", tmp_path / "sessions")
    mexico = {
        "meeting_key": 1298,
        "session_key": 11404,
        "session_name": "Race",
        "country_name": "Mexico",
        "date_start": "2026-11-01T20:00:00Z",
        "date_end": "2026-11-01T22:00:00Z",
        "circuit_short_name": "Mexico City",
        "circuit_key": 65,
        "year": 2026,
    }
    brazil = {
        **mexico,
        "session_key": 11412,
        "date_start": "2026-11-08T17:00:00Z",
        "date_end": "2026-11-08T19:00:00Z",
    }
    unheld = {**mexico, "session_key": 11261}
    request = httpx.Request("GET", f"{openf1_client.BASE_URL}/sessions?year=2026&session_name=Race")
    fetch = Mock(
        side_effect=[
            httpx.Response(200, json=[mexico, unheld], request=request),
            httpx.Response(200, json=[mexico, brazil, unheld], request=request),
            httpx.Response(401, request=request),
        ]
    )
    monkeypatch.setattr(openf1_client.httpx, "get", fetch)

    assert [session.session_key for session in openf1_client.get_sessions(2026)] == [11404]
    openf1_client.get_sessions(2026, refresh=True)
    with pytest.raises(httpx.HTTPStatusError):
        openf1_client.get_sessions(2026, refresh=True)
    assert [session.session_key for session in openf1_client.get_sessions(2026)] == [11412, 11404]


def test_sync_warms_only_completed_races_with_an_incomplete_cache(monkeypatch):
    now = datetime.now(timezone.utc)
    sessions = [
        SimpleNamespace(session_key=3, date_end=now + timedelta(days=1)),
        SimpleNamespace(session_key=2, date_end=now - timedelta(days=1)),
        SimpleNamespace(session_key=1, date_end=now - timedelta(days=2)),
    ]
    get_sessions = Mock(return_value=sessions)
    audit = Mock(side_effect=[{"is_complete": False}, {"is_complete": True}, {"is_complete": True}])
    warm = Mock(return_value=True)
    monkeypatch.setattr(cache_manager, "get_sessions", get_sessions)
    monkeypatch.setattr(cache_manager, "audit_session", audit)
    monkeypatch.setattr(cache_manager, "prewarm_session", warm)

    assert cache_manager.sync_current_season()
    get_sessions.assert_called_once_with(year=now.year, refresh=True)
    warm.assert_called_once_with(2)


def test_audit_requires_a_cache_file_for_each_rostered_driver(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_manager, "CACHE_DIR", tmp_path)
    session_dir = tmp_path / "42"
    for feed in ("car_data", "location"):
        (session_dir / feed).mkdir(parents=True)
        (session_dir / feed / "1.json").write_text(json.dumps(["sample" * 20]), encoding="utf-8")
    for feed in ("sessions", "intervals", "laps", "pit", "position", "race_control", "stints"):
        (session_dir / f"{feed}.json").write_text("[]", encoding="utf-8")
    (session_dir / "track_geometry.json").write_text("{}", encoding="utf-8")
    (session_dir / "drivers.json").write_text(
        json.dumps([{"driver_number": 1}, {"driver_number": 2}]), encoding="utf-8"
    )

    audit = cache_manager.audit_session(42)
    assert not audit["is_complete"]
    assert audit["missing"] == ["car_data/2.json", "location/2.json"]

    for feed in ("car_data", "location"):
        (session_dir / feed / "2.json").write_text("[]", encoding="utf-8")
    assert cache_manager.audit_session(42)["is_complete"]
