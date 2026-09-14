import pitwall_telemetry_engine
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
        return get_latest_race_session().session_key
    
    return int(session_key)

def get_drivers(session_key: str | int = "latest") -> dict[int, Driver]:
    """Fetches drivers for a session and returns a Driver Registry lookup dictionary: {driver_number: Driver}."""
    resolved_key = _resolve_session_key(session_key)

    url = f"{BASE_URL}/drivers?session_key={resolved_key}"
    cache_path = CACHE_DIR/ str(resolved_key) / "drivers.json"
    
    drivers = _fetch_or_cache(cache_path, url)

    driver_registry = {}
    for d in drivers:
        driver_obj = Driver(**d)
        driver_registry[driver_obj.driver_number] = driver_obj

    return driver_registry


def get_session(session_key: str | int = "latest") -> Sessions:
    """Fetches session metadata for a given session_key."""
    resolved_key = _resolve_session_key(session_key)

    url = f"{BASE_URL}/sessions?session_key={resolved_key}"
    cache_path = CACHE_DIR / str(resolved_key) / "sessions.json"

    sessions_data = _fetch_or_cache(cache_path, url)
    
    if not sessions_data:
        raise ValueError(f"No session found for key: {resolved_key}")

    return Sessions(**sessions_data[0])


def get_sessions(year: int | None = 2024, session_name: str | None = "Race") -> list[Sessions]:
    """Fetches a list of Grand Prix sessions filtered by year and/or session name."""
    query_params = []
    if year is not None:
        query_params.append(f"year={year}")
    if session_name is not None:
        query_params.append(f"session_name={session_name}")

    query_str = f"?{'&'.join(query_params)}" if query_params else ""
    url = f"{BASE_URL}/sessions{query_str}"

    year_tag = str(year) if year is not None else "all"
    name_tag = session_name if session_name is not None else "all"
    cache_path = CACHE_DIR.parent / "calendar" / f"sessions_{year_tag}_{name_tag}.json"

    data = _fetch_or_cache(cache_path, url)
    sessions = [Sessions(**s) for s in data]

    # Sort chronologically by start date descending (latest first)
    sessions.sort(key=lambda s: s.date_start, reverse=True)
    return sessions


def get_car_data(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[CarData]:
    """Fetches raw car telemetry ticks for a session (optionally filtered by driver_number)."""
    resolved_key = _resolve_session_key(session_key)

    if driver_number is not None:
        url = f"{BASE_URL}/car_data?session_key={resolved_key}&driver_number={driver_number}"
        cache_path = CACHE_DIR / str(resolved_key) / "car_data" / f"{driver_number}.json"
    else:
        url = f"{BASE_URL}/car_data?session_key={resolved_key}"
        cache_path = CACHE_DIR / str(resolved_key) / "car_data" / "all.json"

    records = _fetch_or_cache(cache_path, url)
    return [CarData(**r) for r in records]


def get_intervals(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Intervals]:
    """Fetches race interval & gap data for a session (optionally filtered by driver_number)."""
    resolved_key = _resolve_session_key(session_key)
    full_cache_path = CACHE_DIR / str(resolved_key) / "intervals.json"

    # Optimization: if full session intervals file exists, load and filter in Python
    if full_cache_path.exists():
        raw_text = full_cache_path.read_text(encoding="utf-8")
        records = json.loads(raw_text)
        if driver_number is not None:
            records = [r for r in records if r.get("driver_number") == driver_number]
        return [Intervals(**r) for r in records]

    if driver_number is not None:
        url = f"{BASE_URL}/intervals?session_key={resolved_key}&driver_number={driver_number}"
        cache_path = CACHE_DIR / str(resolved_key) / f"intervals_{driver_number}.json"
    else:
        url = f"{BASE_URL}/intervals?session_key={resolved_key}"
        cache_path = full_cache_path

    records = _fetch_or_cache(cache_path, url)
    return [Intervals(**r) for r in records]


def get_race_control(session_key: str | int = "latest") -> list[RaceControlMessage]:
    """Fetches FIA Race Control messages and flag events for a session."""
    resolved_key = _resolve_session_key(session_key)
    url = f"{BASE_URL}/race_control?session_key={resolved_key}"
    cache_path = CACHE_DIR / str(resolved_key) / "race_control.json"

    records = _fetch_or_cache(cache_path, url)
    return [RaceControlMessage(**r) for r in records]


def get_location(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Location]:
    """Fetches Cartesian GPS coordinates (X, Y, Z) for track positioning."""
    resolved_key = _resolve_session_key(session_key)
    full_cache_path = CACHE_DIR / str(resolved_key) / "location.json"

    # Optimization: if full session location file exists, load and filter in Python
    if full_cache_path.exists():
        raw_text = full_cache_path.read_text(encoding="utf-8")
        records = json.loads(raw_text)
        if driver_number is not None:
            records = [r for r in records if r.get("driver_number") == driver_number]
        return [Location(**r) for r in records]

    if driver_number is not None:
        url = f"{BASE_URL}/location?session_key={resolved_key}&driver_number={driver_number}"
        cache_path = CACHE_DIR / str(resolved_key) / f"location_{driver_number}.json"
    else:
        url = f"{BASE_URL}/location?session_key={resolved_key}"
        cache_path = full_cache_path

    records = _fetch_or_cache(cache_path, url)
    return [Location(**r) for r in records]


def get_track_geometry(session_key: str | int = "latest", sample_driver: int | None = None) -> dict:
    """
    Extracts and normalizes circuit track geometry points from location data.
    Caches the pre-calculated geometry directly to avoid re-downsampling 50k points on each call.
    Returns:
      {
        "points": [{"x": float, "y": float}, ...],
        "bounds": {"min_x": float, "max_x": float, "min_y": float, "max_y": float}
      }
    """
    resolved_key = _resolve_session_key(session_key)
    cache_path = CACHE_DIR / str(resolved_key) / "track_geometry.json"

    if cache_path.exists():
        raw_text = cache_path.read_text(encoding="utf-8")
        return json.loads(raw_text)

    # If no sample driver is given, pick the first driver in the registry
    if sample_driver is None:
        registry = get_drivers(resolved_key)
        sample_driver = next(iter(registry.keys())) if registry else None

    # Fetch sample location points for a single driver
    locs = get_location(resolved_key, driver_number=sample_driver)
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

    geometry = {
        "points": [{"x": p.x, "y": p.y} for p in sampled],
        "bounds": bounds,
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(geometry), encoding="utf-8")

    return geometry


def get_laps(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Laps]:
    """Fetches lap timings, sector durations, and speed trap figures for a session."""
    resolved_key = _resolve_session_key(session_key)
    full_cache_path = CACHE_DIR / str(resolved_key) / "laps.json"

    if full_cache_path.exists():
        raw_text = full_cache_path.read_text(encoding="utf-8")
        records = json.loads(raw_text)
        if driver_number is not None:
            records = [r for r in records if r.get("driver_number") == driver_number]
        return [Laps(**r) for r in records]

    if driver_number is not None:
        url = f"{BASE_URL}/laps?session_key={resolved_key}&driver_number={driver_number}"
        cache_path = CACHE_DIR / str(resolved_key) / f"laps_{driver_number}.json"
    else:
        url = f"{BASE_URL}/laps?session_key={resolved_key}"
        cache_path = full_cache_path

    records = _fetch_or_cache(cache_path, url)
    return [Laps(**r) for r in records]


def get_stints(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[Stints]:
    """Fetches tire stint records (compound, start/end lap, tire age) for a session."""
    resolved_key = _resolve_session_key(session_key)
    full_cache_path = CACHE_DIR / str(resolved_key) / "stints.json"

    if full_cache_path.exists():
        raw_text = full_cache_path.read_text(encoding="utf-8")
        records = json.loads(raw_text)
        if driver_number is not None:
            records = [r for r in records if r.get("driver_number") == driver_number]
        return [Stints(**r) for r in records]

    if driver_number is not None:
        url = f"{BASE_URL}/stints?session_key={resolved_key}&driver_number={driver_number}"
        cache_path = CACHE_DIR / str(resolved_key) / f"stints_{driver_number}.json"
    else:
        url = f"{BASE_URL}/stints?session_key={resolved_key}"
        cache_path = full_cache_path

    records = _fetch_or_cache(cache_path, url)
    return [Stints(**r) for r in records]


def warm_session_cache(session_key: str | int = "latest", driver_numbers: list[int] | None = None) -> None:
    """
    Preloads and caches all core datasets for a session to local disk.
    Guarantees 0ms network latency during live replay and on-the-fly driver switching.
    """
    resolved_key = _resolve_session_key(session_key)

    # 1. Session metadata & Driver roster
    get_session(resolved_key)
    registry = get_drivers(resolved_key)

    # 2. Macro race datasets (Full 20-car field)
    get_track_geometry(resolved_key)
    get_location(resolved_key)
    get_intervals(resolved_key)
    get_laps(resolved_key)
    get_stints(resolved_key)
    get_race_control(resolved_key)

    # 3. High-frequency telemetry for active or specified drivers
    target_drivers = driver_numbers if driver_numbers is not None else list(registry.keys())
    for d_num in target_drivers:
        get_car_data(resolved_key, driver_number=d_num)


@lru_cache(maxsize=1)
def get_latest_race_session() -> Sessions:
    """
    Fetches the most recent Grand Prix Race that has already started or completed.
    Filters out practice, qualifying, and future scheduled races.
    """
    now = datetime.now(timezone.utc).isoformat()
    url = f"{BASE_URL}/sessions?session_name=Race"
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
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