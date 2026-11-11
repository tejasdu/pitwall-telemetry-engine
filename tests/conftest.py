import json
from datetime import datetime, timezone

import httpx
import pytest

from pitwall_telemetry_engine.ingestion import cache_manager, openf1_client
from pitwall_telemetry_engine.ingestion.timeline_replayer import SessionCache


@pytest.fixture(autouse=True)
def isolated_cache_and_http(tmp_path, monkeypatch):
    cache_dir = tmp_path / "sessions"
    monkeypatch.setattr(openf1_client, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(cache_manager, "CACHE_DIR", cache_dir)

    def reject_http(transport, request):
        pytest.fail(f"Unexpected outbound HTTP request: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_http)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_http)
    return cache_dir


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


@pytest.fixture
def race_cache(isolated_cache_and_http):
    session_key = 1
    common = {"session_key": session_key, "meeting_key": 1}
    session_dir = isolated_cache_and_http / str(session_key)

    def write_records(filename, records):
        destination = session_dir / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps([{**common, **row} for row in records]), encoding="utf-8")

    write_records(
        "sessions.json",
        [
            {
                "session_name": "Race",
                "country_name": "Test",
                "circuit_short_name": "Test",
                "circuit_key": 1,
                "year": 2026,
                "date_start": iso(100),
                "date_end": iso(300),
            }
        ],
    )
    drivers = (1, 16, 55)
    write_records(
        "drivers.json",
        [
            {
                "driver_number": number,
                "full_name": f"Driver {number}",
                "name_acronym": f"D{number}",
                "team_name": "Test",
            }
            for number in drivers
        ],
    )
    write_records(
        "position.json",
        [
            {"driver_number": number, "date": iso(100), "position": position}
            for position, number in enumerate(drivers, start=1)
        ],
    )
    write_records(
        "intervals.json",
        [
            {
                "driver_number": number,
                "date": iso(110),
                "interval": gap,
                "gap_to_leader": leader_gap,
            }
            for number, gap, leader_gap in [(1, None, None), (16, 2.0, 2.0), (55, 0.6, 2.6)]
        ],
    )
    for number in drivers:
        sample = {"driver_number": number, "date": iso(110)}
        write_records(f"location/{number}.json", [{**sample, "x": 10, "y": 20, "z": 0}])
        write_records(
            f"car_data/{number}.json",
            [{**sample, "brake": 100, "n_gear": 4, "rpm": 10000, "speed": 200, "throttle": 0}],
        )
    write_records("pit.json", [])
    write_records("race_control.json", [])
    write_records(
        "laps.json",
        [
            {"driver_number": 1, "lap_number": 1, "date_start": iso(100), "lap_duration": 60},
            {"driver_number": 1, "lap_number": 2, "date_start": iso(160), "lap_duration": 60},
            {"driver_number": 16, "lap_number": 2, "date_start": iso(165), "lap_duration": 60},
        ],
    )
    write_records(
        "stints.json",
        [
            {
                "driver_number": number,
                "stint_number": stint,
                "lap_start": stint,
                "compound": compound,
            }
            for number in (1, 16)
            for stint, compound in [(1, "SOFT"), (2, "HARD")]
        ],
    )
    return SessionCache(), session_key
