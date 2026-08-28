from pitwall_telemetry_engine.schemas.car_data import CarData

def calculate_deceleration(prev_tick: CarData, curr_tick: CarData) -> float | None:
    """
    Calculates speed deceleration rate (km/h per second) between two ticks.
    Returns None if time gap is zero or invalid.
    """

    delta_t = (curr_tick.date - prev_tick.date).total_seconds()
    if delta_t <= 0:
        return None
    delta_v = curr_tick.speed - prev_tick.speed
    deceleration_rate = delta_v / delta_t
    return deceleration_rate

def is_heavy_braking(curr_tick: CarData, deceleration_rate: float | None) -> bool:
    if curr_tick.brake > 0.5:
    
    
