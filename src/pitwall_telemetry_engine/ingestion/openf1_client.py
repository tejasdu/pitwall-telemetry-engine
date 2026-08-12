import httpx
from pitwall_telemetry_engine.schemas.driver import Driver
from pitwall_telemetry_engine.schemas.car_data import CarData
from pitwall_telemetry_engine.schemas.intervals import Intervals
from pitwall_telemetry_engine.schemas.sessions import Sessions

BASE_URL = "https://api.openf1.org/v1"
DEFAULT_TIMEOUT = 30.0  # 30 seconds timeout for large API payloads


def get_drivers(session_key: str | int = "latest") -> dict[int, Driver]:
    """Fetches drivers for a session and returns a Driver Registry lookup dictionary: {driver_number: Driver}."""
    url = f"{BASE_URL}/drivers?session_key={session_key}"
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    drivers = response.json()

    driver_registry = {}
    for d in drivers:
        driver_obj = Driver(**d)
        driver_registry[driver_obj.driver_number] = driver_obj

    return driver_registry


def get_session(session_key: str | int = "latest") -> Sessions:
    """Fetches session metadata for a given session_key."""
    url = f"{BASE_URL}/sessions?session_key={session_key}"
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
    sessions_data = response.json()
    if not sessions_data:
        raise ValueError(f"No session found for key: {session_key}")
    return Sessions(**sessions_data[0])


def get_car_data(
    session_key: str | int = "latest", driver_number: int | None = None
) -> list[CarData]:
    """Fetches raw car telemetry ticks for a session (optionally filtered by driver_number)."""
    url = f"{BASE_URL}/car_data?session_key={session_key}"
    if driver_number is not None:
        url += f"&driver_number={driver_number}"

    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
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
    records = response.json()
    return [Intervals(**r) for r in records]