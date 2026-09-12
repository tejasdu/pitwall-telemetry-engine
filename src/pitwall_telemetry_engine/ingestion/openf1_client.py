from pitwall_telemetry_engine.schemas import sessions
from datetime import datetime, timezone
from functools import lru_cache
import httpx
import json
from pathlib import Path
from pitwall_telemetry_engine.schemas.car_data import CarData
from pitwall_telemetry_engine.schemas.driver import Driver
from pitwall_telemetry_engine.schemas.intervals import Intervals
from pitwall_telemetry_engine.schemas.laps import Laps
from pitwall_telemetry_engine.schemas.location import Location
from pitwall_telemetry_engine.schemas.race_control import RaceControlMessage
from pitwall_telemetry_engine.schemas.sessions import Sessions
from pitwall_telemetry_engine.schemas.stints import Stints

BASE_URL = "https://api.openf1.org/v1"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)  
CACHE_DIR = Path(__file__).parent.parent.parent.parent / ".cache" / "sessions"

def _fetch_or_cache(cache_file_path: Path, url: str) -> list[dict] | dict:
    # 1. If cache hit, read from the file
    if cache_file_path.exists():
        raw_text = cache_file_path.read_text(encoding="utf-8")
        return json.loads(raw_text)

    # 2. Cache miss: call OpenF1 API to get data
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    # 3. Save to disk for next time
    cache_file_path.parent.mkdir(parents=True, exist_ok=True)
    cache_file_path.write_text(json.dumps(data), encoding="utf-8")

    return data

def _resolve_session_key(session_key: str | int = "latest") -> int:
    if session_key == "latest" or session_key == "":
        return get_latest_race_session().sessionkey
    
    return int(session_key)

def get_drivers(session_key: str | int = "latest") -> dict[int, Driver]:
    """Fetches drivers for a session and returns a Driver Registry lookup dictionary: {driver_number: Driver}."""

    url = f"{BASE_URL}/drivers?session_key={session_key}"
    cache_path = CACHE_DIR/ str(session_key) / "drivers.json"
    
    drivers = _fetch_or_cache(cache_path, url)

    driver_registry = {}
    for d in drivers:
        driver_obj = Driver(**d)
        driver_registry[driver_obj.driver_number] = driver_obj

    return driver_registry


def get_session(session_key: str | int = "latest") -> Sessions:
    """Fetches session metadata for a given session_key."""
    url = f"{BASE_URL}/sessions?session_key={session_key}"
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()

    sessions_data = response.json()
    if not sessions_data:
        raise ValueError(f"No session found for key: {session_key}")

    return Sessions(**sessions_data[0])


def get_sessions( year: int | None = 2024, session_name: str | None = "Race") -> list[Sessions]:
    """Fetches a list of Grand Prix sessions filtered by year and/or session name."""

    query_params = []
    if year is not None:
        query_params.append(f"year={year}")
    if session_name is not None:
        query_params.append(f"session_name={session_name}")

    query_str = f"?{'&'.join(query_params)}" if query_params else ""
    url = f"{BASE_URL}/sessions{query_str}"

    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    sessions = [Sessions(**s) for s in data]

    # Sort chronologically by start date descending (latest first)
    sessions.sort(key=lambda s: s.date_start, reverse=True)
    return sessions


def get_car_data(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[CarData]:
    """Fetches raw car telemetry ticks for a session (optionally filtered by driver_number)."""
    url = f"{BASE_URL}/car_data?session_key={session_key}"
    if driver_number is not None:
        url += f"&driver_number={driver_number}"

    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()

    records = response.json()
    return [CarData(**r) for r in records]


def get_intervals(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Intervals]:
    """Fetches race interval & gap data for a session (optionally filtered by driver_number)."""
    url = f"{BASE_URL}/intervals?session_key={session_key}"
    if driver_number is not None:
        url += f"&driver_number={driver_number}"

    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()

    records = response.json()
    return [Intervals(**r) for r in records]


def get_race_control(session_key: str | int = "latest") -> list[RaceControlMessage]:
    """Fetches FIA Race Control messages and flag events for a session."""
    url = f"{BASE_URL}/race_control?session_key={session_key}"
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()

    records = response.json()
    return [RaceControlMessage(**r) for r in records]


def get_location(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Location]:
    """Fetches Cartesian GPS coordinates (X, Y, Z) for track positioning."""
    url = f"{BASE_URL}/location?session_key={session_key}"
    if driver_number is not None:
        url += f"&driver_number={driver_number}"

    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    
    records = response.json()
    return [Location(**r) for r in records]


def get_track_geometry(session_key: str | int = "latest", sample_driver: int | None = None) -> dict:
    """
    Extracts and normalizes circuit track geometry points from location data.
    Returns:
      {
        "points": [{"x": float, "y": float}, ...],
        "bounds": {"min_x": float, "max_x": float, "min_y": float, "max_y": float}
      }
    """
    
    # Fetch sample location points
    locs = get_location(session_key, driver_number=sample_driver)
    # Filter out stationary / zero coordinates

    valid_points = [p for p in locs if p.x != 0 or p.y != 0]

    if not valid_points:
        return {"points": [], "bounds": {"min_x": 0, "max_x": 1, "min_y": 0, "max_y": 1}}

    # Downsample points for smooth 60 FPS Canvas path rendering (~800 points is optimal)
    step = max(1, len(valid_points) // 800)
    sampled = valid_points[::step]

    xs = [p.x for p in valid_points]
    ys = [p.y for p in valid_points]

    bounds = {
        "min_x": float(min(xs)),
        "max_x": float(max(xs)),
        "min_y": float(min(ys)),
        "max_y": float(max(ys)),
    }

    return {
        "points": [{"x": p.x, "y": p.y} for p in sampled],
        "bounds": bounds,
    }


def get_laps(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Laps]:
    """Fetches lap timings, sector durations, and speed trap figures for a session."""
    url = f"{BASE_URL}/laps?session_key={session_key}"
    if driver_number is not None:
        url += f"&driver_number={driver_number}"

    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    records = response.json()
    return [Laps(**r) for r in records]


def get_stints(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Stints]:
    """Fetches tire stint records (compound, start/end lap, tire age) for a session."""
    url = f"{BASE_URL}/stints?session_key={session_key}"
    if driver_number is not None:
        url += f"&driver_number={driver_number}"

    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    records = response.json()
    return [Stints(**r) for r in records]


def get_latest_race_session() -> Sessions:
    """
    Fetches the most recent Grand Prix Race that has already started or completed.
    Filters out practice, qualifying, and future scheduled races.
    """
    now = datetime.now(timezone.utc).isoformat()
    url = f"{BASE_URL}/sessions?session_name=Race"
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    data = response.json()

    # Filter for completed or active Grand Prix races in the past
    valid_races = [
        s
        for s in data
        if s.get("date_start")
        and s["date_start"] <= now
        and not s.get("is_cancelled", False)
    ]
    if not valid_races:
        valid_races = data

    # Sort descending by start date (latest first)
    valid_races.sort(key=lambda s: s["date_start"], reverse=True)
    
    return Sessions(**valid_races[0])