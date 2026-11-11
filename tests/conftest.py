import json
from datetime import datetime, timezone
from functools import partial

import httpx
import pytest

from pitwall_telemetry_engine.ingestion import cache_manager, openf1_client
from pitwall_telemetry_engine.ingestion.timeline_replayer import SessionCache


def pytest_addoption(parser):
    parser.addoption("--run-browser", action="store_true", help="Run Chromium smoke tests")
    parser.addoption("--run-openf1", action="store_true", help="Run live OpenF1 integration tests")


@pytest.fixture(autouse=True)
def isolated_cache_and_http(tmp_path, monkeypatch, request):
    if request.node.get_closest_marker("browser") and not request.config.getoption("--run-browser"):
        pytest.skip("Browser smoke test requires --run-browser")

    cache_dir = tmp_path / "sessions"
    monkeypatch.setattr(openf1_client, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(cache_manager, "CACHE_DIR", cache_dir)

    if request.node.get_closest_marker("openf1_live"):
        if not request.config.getoption("--run-openf1"):
            pytest.skip("Live OpenF1 check requires --run-openf1")
        return cache_dir

    def reject_http(transport, request):
        pytest.fail(f"Unexpected outbound HTTP request: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_http)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_http)
    return cache_dir


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def write_race(cache_dir, session_key, country="Test", start=100, drivers=(1, 16, 55)):
    common = {"session_key": session_key, "meeting_key": 1}
    session_dir = cache_dir / str(session_key)

    def race_time(offset):
        return iso(start + offset)

    def write_records(filename, records):
        destination = session_dir / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps([{**common, **row} for row in records]), encoding="utf-8")

    session = {
        "session_name": "Race",
        "country_name": country,
        "circuit_short_name": country,
        "circuit_key": session_key,
        "year": 2026,
        "date_start": race_time(0),
        "date_end": race_time(200),
    }
    write_records("sessions.json", [session])
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
            {"driver_number": number, "date": race_time(0), "position": position}
            for position, number in enumerate(drivers, start=1)
        ],
    )
    write_records(
        "intervals.json",
        [
            {
                "driver_number": number,
                "date": race_time(10),
                "interval": gap,
                "gap_to_leader": leader_gap,
            }
            for number, gap, leader_gap in zip(
                drivers, (None, 2.0, 0.6), (None, 2.0, 2.6), strict=True
            )
        ],
    )
    for number in drivers:
        sample = {"driver_number": number, "date": race_time(10)}
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
            {
                "driver_number": drivers[0],
                "lap_number": 1,
                "date_start": race_time(0),
                "lap_duration": 60,
            },
            {
                "driver_number": drivers[0],
                "lap_number": 2,
                "date_start": race_time(60),
                "lap_duration": 60,
            },
            {
                "driver_number": drivers[1],
                "lap_number": 2,
                "date_start": race_time(65),
                "lap_duration": 60,
            },
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
            for number in drivers[:2]
            for stint, compound in [(1, "SOFT"), (2, "HARD")]
        ],
    )
    return {**common, **session}


@pytest.fixture
def write_cached_race(isolated_cache_and_http):
    return partial(write_race, isolated_cache_and_http)


@pytest.fixture
def race_cache(write_cached_race):
    session = write_cached_race(session_key=1)
    return SessionCache(), session["session_key"]
