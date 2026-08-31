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
    ["driver_number", "driver_name", "team_name"],
)

CAR_BRAKE = Gauge(
    "f1_car_brake_active",
    "Brake pedal engaged status (0 or 1)",
    ["driver_number", "driver_name", "team_name"],
)

CAR_RPM = Gauge(
    "f1_car_rpm",
    "Engine revolutions per minute",
    ["driver_number", "driver_name", "team_name"],
)

CAR_GEAR = Gauge(
    "f1_car_gear",
    "Current gear selection (0-8)",
    ["driver_number", "driver_name", "team_name"],
)

CAR_DRS_STATUS = Gauge(
    "f1_drs_status",
    "DRS flap status (0=Closed/Off, 1=Eligible/Open)",
    ["driver_number", "driver_name", "team_name"],
)

CAR_DECELERATION = Gauge(
    "f1_car_deceleration_rate",
    "Speed deceleration rate in km/h per second",
    ["driver_number", "driver_name", "team_name"],
)

CAR_INTERVAL_GAP = Gauge(
    "f1_interval_gap_seconds",
    "Timing interval gap to car ahead in seconds",
    ["driver_number", "driver_name", "team_name"],
)

DRS_THREAT_ACTIVE = Gauge(
    "f1_drs_threat_active",
    "DRS attack threat window active status (1 if gap <= 1.0s, else 0)",
    ["driver_number", "driver_name", "team_name"],
)

RACE_STATUS = Gauge(
    "f1_race_status_code",
    "Race control status code (0=GREEN, 1=YELLOW, 2=RED, 3=SAFETY CAR, 4=VSC, 5=CHEQUERED)",
)

# 2. Prometheus Counters (Cumulative Event Tracking)
HEAVY_BRAKING_TOTAL = Counter(
    "f1_heavy_braking_events_total",
    "Total number of heavy braking events detected",
    ["driver_number", "driver_name", "team_name"],
)

TELEMETRY_TICKS_TOTAL = Counter(
    "f1_telemetry_ticks_ingested_total",
    "Total telemetry ticks processed",
    ["driver_number", "driver_name", "team_name"],
)


def start_metrics_server(port: int = 8000) -> None:
    """Starts the background HTTP server exposing Prometheus metrics on /metrics."""
    start_http_server(port)
    print(f"📊 Prometheus metrics exporter listening on http://localhost:{port}/metrics\n")


def update_race_status(flag: str | None = None, message: str | None = None) -> None:
    """
    Updates the race status code gauge:
    0: GREEN (Track Clear / Normal Racing)
    1: YELLOW (Sector / Track Caution)
    2: RED (Race Suspended / Cars in Pit Lane)
    3: SAFETY CAR
    4: VIRTUAL SAFETY CAR (VSC)
    5: CHEQUERED
    """
    flag_str = (flag or "").upper()
    msg_str = (message or "").upper()

    code = 0
    if "RED" in flag_str or "RED" in msg_str or "SUSPENDED" in msg_str:
        code = 2
    elif "SAFETY CAR" in flag_str or "SAFETY CAR" in msg_str:
        code = 3
    elif "VSC" in flag_str or "VIRTUAL" in msg_str:
        code = 4
    elif "CHEQUERED" in flag_str or "CHEQUERED" in msg_str:
        code = 5
    elif "YELLOW" in flag_str or "YELLOW" in msg_str:
        code = 1
    elif "CLEAR" in flag_str or "GREEN" in flag_str:
        code = 0

    RACE_STATUS.set(code)


def update_telemetry_metrics(
    tick: CarData,
    driver: Driver | None = None,
    decel: float | None = None,
    is_heavy_brake: bool = False,
    interval_gap: float | None = None,
    is_drs_window: bool = False,
) -> None:
    """Updates Prometheus gauges and counters for a given telemetry tick."""
    drv_num = str(tick.driver_number)
    drv_name = driver.full_name if driver else f"Driver #{drv_num}"
    team_name = driver.team_name if driver and driver.team_name else "Unknown Team"

    lbls = {"driver_number": drv_num, "driver_name": drv_name, "team_name": team_name}

    # Update Gauges
    CAR_SPEED.labels(**lbls).set(tick.speed)
    CAR_THROTTLE.labels(**lbls).set(tick.throttle)
    CAR_BRAKE.labels(**lbls).set(1 if tick.brake > 0 else 0)
    CAR_RPM.labels(**lbls).set(tick.rpm)
    CAR_GEAR.labels(**lbls).set(tick.n_gear)

    # DRS status (1 if active/open, 0 if closed/none)
    drs_val = 1 if tick.drs is not None and tick.drs in (8, 10, 12, 14) else 0
    CAR_DRS_STATUS.labels(**lbls).set(drs_val)

    if decel is not None:
        CAR_DECELERATION.labels(**lbls).set(decel)

    # Interval Gap and DRS Threat Window
    if interval_gap is not None:
        CAR_INTERVAL_GAP.labels(**lbls).set(interval_gap)
    DRS_THREAT_ACTIVE.labels(**lbls).set(1 if is_drs_window else 0)

    # Update Counters
    TELEMETRY_TICKS_TOTAL.labels(**lbls).inc()
    if is_heavy_brake:
        HEAVY_BRAKING_TOTAL.labels(**lbls).inc()
