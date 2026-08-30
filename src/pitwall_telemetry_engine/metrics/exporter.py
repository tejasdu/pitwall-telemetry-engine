from prometheus_client import Counter, Gauge, start_http_server
from pitwall_telemetry_engine.schemas.car_data import CarData
from pitwall_telemetry_engine.schemas.driver import Driver

# 1. Prometheus Gauges (Real-Time Current Values)
CAR_SPEED = Gauge(
    "f1_car_speed_kmh",
    "Real-time vehicle speed in km/h",
    ["driver_number", "driver_name", "team_name"],
)

CAR_THROTTLE = Gauge(
    "f1_car_throttle_pct",
    "Throttle pedal application percentage (0-100%)",
    ["driver_number"],
)

CAR_BRAKE = Gauge(
    "f1_car_brake_active",
    "Brake pedal engaged status (0 or 1)",
    ["driver_number"],
)

CAR_RPM = Gauge(
    "f1_car_rpm",
    "Engine revolutions per minute",
    ["driver_number"],
)

CAR_GEAR = Gauge(
    "f1_car_gear",
    "Current gear selection (0-8)",
    ["driver_number"],
)

CAR_DRS_STATUS = Gauge(
    "f1_drs_status",
    "DRS flap status (0=Closed/Off, 1=Eligible/Open)",
    ["driver_number"],
)

CAR_DECELERATION = Gauge(
    "f1_car_deceleration_rate",
    "Speed deceleration rate in km/h per second",
    ["driver_number"],
)

# 2. Prometheus Counters (Cumulative Event Tracking)
HEAVY_BRAKING_TOTAL = Counter(
    "f1_heavy_braking_events_total",
    "Total number of heavy braking events detected",
    ["driver_number", "team_name"],
)

TELEMETRY_TICKS_TOTAL = Counter(
    "f1_telemetry_ticks_ingested_total",
    "Total telemetry ticks processed",
    ["driver_number"],
)


def start_metrics_server(port: int = 8000) -> None:
    """Starts the background HTTP server exposing Prometheus metrics on /metrics."""
    start_http_server(port)
    print(f"📊 Prometheus metrics exporter listening on http://localhost:{port}/metrics\n")


def update_telemetry_metrics(
    tick: CarData,
    driver: Driver | None = None,
    decel: float | None = None,
    is_heavy_brake: bool = False,
) -> None:
    """Updates Prometheus gauges and counters for a given telemetry tick."""
    drv_num = str(tick.driver_number)
    drv_name = driver.full_name if driver else f"Driver #{drv_num}"
    team_name = driver.team_name if driver and driver.team_name else "Unknown Team"

    # Update Gauges
    CAR_SPEED.labels(driver_number=drv_num, driver_name=drv_name, team_name=team_name).set(tick.speed)
    CAR_THROTTLE.labels(driver_number=drv_num).set(tick.throttle)
    CAR_BRAKE.labels(driver_number=drv_num).set(1 if tick.brake > 0 else 0)
    CAR_RPM.labels(driver_number=drv_num).set(tick.rpm)
    CAR_GEAR.labels(driver_number=drv_num).set(tick.n_gear)

    # DRS status (1 if active/open, 0 if closed/none)
    drs_val = 1 if tick.drs is not None and tick.drs in (8, 10, 12, 14) else 0
    CAR_DRS_STATUS.labels(driver_number=drv_num).set(drs_val)

    if decel is not None:
        CAR_DECELERATION.labels(driver_number=drv_num).set(decel)

    # Update Counters
    TELEMETRY_TICKS_TOTAL.labels(driver_number=drv_num).inc()
    if is_heavy_brake:
        HEAVY_BRAKING_TOTAL.labels(driver_number=drv_num, team_name=team_name).inc()
