from pitwall_telemetry_engine.schemas.car_data import CarData
from pitwall_telemetry_engine.schemas.intervals import Intervals


def calculate_deceleration(prev_tick: CarData, curr_tick: CarData) -> float | None:
    """
    Calculates speed deceleration rate (km/h per second) between two ticks.
    Returns a negative number during deceleration, or None if time gap is invalid.
    """
    delta_t = (curr_tick.date - prev_tick.date).total_seconds()
    if delta_t <= 0:
        return None

    delta_v = curr_tick.speed - prev_tick.speed
    return delta_v / delta_t


def is_heavy_braking(
    curr_tick: CarData,
    deceleration_rate: float | None,
    threshold: float = -40.0,
) -> bool:
    """
    Returns True if the driver is actively on the brake pedal AND decelerating
    faster than the threshold (e.g. dropping >40 km/h per second) while moving on track.
    """
    if deceleration_rate is None:
        return False
    return 0 < curr_tick.brake <= 100 and deceleration_rate < threshold and curr_tick.speed > 30


def calculate_acceleration(prev_tick: CarData, curr_tick: CarData) -> float | None:
    """
    Calculates speed acceleration rate (km/h per second) between two ticks.
    Returns a positive number during acceleration, or None if time gap is invalid.
    """
    delta_t = (curr_tick.date - prev_tick.date).total_seconds()
    if delta_t <= 0:
        return None

    delta_v = curr_tick.speed - prev_tick.speed
    return delta_v / delta_t


def is_full_throttle(curr_tick: CarData) -> bool:
    """
    Returns True if the car is pinned at wide open throttle (>= 98%) while driving in gear.
    """
    return 98 <= curr_tick.throttle <= 100 and curr_tick.n_gear > 0 and curr_tick.speed > 30


def is_drs_threat(interval_data: Intervals, threshold: float = 1.0) -> bool:
    """
    Returns True if the trailing car is within DRS attack proximity (<= 1.000s).
    """
    if isinstance(interval_data.interval, (int, float)):
        return 0.0 < interval_data.interval <= threshold
    return False


def detect_gear_shift(prev_tick: CarData, curr_tick: CarData) -> tuple[bool, int, int] | None:
    """
    Detects if a gear change occurred between ticks.
    Returns (True, prev_gear, curr_gear) if changed, else None.
    """
    if prev_tick.n_gear != curr_tick.n_gear:
        return (True, prev_tick.n_gear, curr_tick.n_gear)
    return None
