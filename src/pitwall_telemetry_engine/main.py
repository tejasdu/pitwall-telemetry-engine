import asyncio
from pitwall_telemetry_engine.ingestion.openf1_client import (
    get_car_data,
    get_drivers,
    get_intervals,
    get_session,
)
from pitwall_telemetry_engine.ingestion.replay import stream_telemetry
from pitwall_telemetry_engine.metrics.exporter import (
    start_metrics_server,
    update_telemetry_metrics,
)
from pitwall_telemetry_engine.metrics.inferences import (
    calculate_deceleration,
    is_full_throttle,
    is_heavy_braking,
)


async def run_engine() -> None:
    session = get_session("latest")
    drivers = get_drivers(session.session_key)

    # Multi-Driver Battle Setup: Carlos Sainz (#55) vs Max Verstappen (#1)
    driver_a_num = 55
    driver_b_num = 1

    drv_a = drivers.get(driver_a_num)
    drv_b = drivers.get(driver_b_num)

    label_a = f"{drv_a.name_acronym} (#{driver_a_num}) [{drv_a.team_name}]" if drv_a else f"#{driver_a_num}"
    label_b = f"{drv_b.name_acronym} (#{driver_b_num}) [{drv_b.team_name}]" if drv_b else f"#{driver_b_num}"

    print("=" * 75)
    print(f" 🏎️  PITWALL MULTI-DRIVER LIVE BATTLE STREAM (10x Speed)")
    print(f"     Circuit : {session.circuit_short_name} ({session.year})")
    print(f"     Battle  : {label_a}  ⚔️   {label_b}")
    print(f"     Start   : {session.date_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 75 + "\n")

    # 1. Start background Prometheus Metrics HTTP server
    start_metrics_server(port=8000)

    # 2. Fetch and filter telemetry for both drivers
    print(f"📥 Fetching race telemetry for #{driver_a_num} and #{driver_b_num}...")
    ticks_a = get_car_data(session.session_key, driver_number=driver_a_num)
    ticks_b = get_car_data(session.session_key, driver_number=driver_b_num)

    race_ticks_a = [t for t in ticks_a if t.date >= session.date_start]
    race_ticks_b = [t for t in ticks_b if t.date >= session.date_start]

    # 3. Merge & sort chronologically into a single synchronized stream
    combined_ticks = sorted(race_ticks_a + race_ticks_b, key=lambda t: t.date)
    print(
        f"📊 Combined {len(combined_ticks)} synchronized battle ticks "
        f"({len(race_ticks_a)} for #{driver_a_num}, {len(race_ticks_b)} for #{driver_b_num}).\n"
    )

    # 4. State tracking per driver
    prev_ticks = {}

    async for curr_tick in stream_telemetry(combined_ticks, playback_factor=10.0):
        drv_num = curr_tick.driver_number
        drv = drivers.get(drv_num)
        drv_tag = f"[{drv.name_acronym:>3}]" if drv else f"[#{drv_num:>2}]"

        prev_tick = prev_ticks.get(drv_num)
        alerts = []
        decel = None
        heavy_brake = False

        if prev_tick is not None:
            decel = calculate_deceleration(prev_tick, curr_tick)
            heavy_brake = is_heavy_braking(curr_tick, decel, threshold=-40.0)
            if heavy_brake:
                alerts.append(f"🚨 HEAVY BRAKE: {decel:6.1f} km/h/s")

        if is_full_throttle(curr_tick):
            alerts.append("⚡ FULL THROTTLE")

        # Update Prometheus Gauges and Counters for this specific driver
        update_telemetry_metrics(
            tick=curr_tick,
            driver=drv,
            decel=decel,
            is_heavy_brake=heavy_brake,
        )

        alert_str = f" | {' | '.join(alerts)}" if alerts else ""

        print(
            f"{drv_tag} [{curr_tick.date.strftime('%H:%M:%S.%f')[:-3]}] "
            f"Speed: {curr_tick.speed:3d} km/h | "
            f"Throttle: {curr_tick.throttle:3d}% | "
            f"Brake: {curr_tick.brake:3d}% | "
            f"Gear: {curr_tick.n_gear} | "
            f"RPM: {curr_tick.rpm:5d}"
            f"{alert_str}"
        )

        # Update driver's state
        prev_ticks[drv_num] = curr_tick


def main() -> None:
    asyncio.run(run_engine())


if __name__ == "__main__":
    main()
