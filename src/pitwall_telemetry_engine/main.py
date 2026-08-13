from pitwall_telemetry_engine.ingestion.openf1_client import (
    get_car_data,
    get_drivers,
    get_intervals,
    get_session,
)


def main() -> None:
    print("=" * 60)
    print(" 🏎️  PITWALL TELEMETRY ENGINE — INITIALIZATION")
    print("=" * 60)

    # 1. Fetch Session Metadata
    print("\n[1/4] Fetching Active Session Metadata...")
    session = get_session("latest")
    print(f"      📍 Circuit  : {session.circuit_short_name} ({session.country_name})")
    print(f"      🏁 Session  : {session.session_name} {session.year}")

    # 2. Build Driver Registry
    print("\n[2/4] Building Driver Registry...")
    drivers = get_drivers(session.session_key)
    print(f"      🏎️  Registered {len(drivers)} drivers on the grid.")
    for num, drv in list(drivers.items())[:5]:
        print(f"         #{num:2d} | {drv.name_acronym} ({drv.full_name}) - {drv.team_name}")

    # 3. Fetch Car Telemetry (e.g. Carlos Sainz #55)
    target_driver = 55
    drv_info = drivers.get(target_driver)
    driver_name = drv_info.full_name if drv_info else f"Driver #{target_driver}"
    team_name = drv_info.team_name if drv_info else "Unknown Team"

    print(f"\n[3/4] Ingesting Live Telemetry for {driver_name} ({team_name})...")
    car_ticks = get_car_data(session.session_key, driver_number=target_driver)
    print(f"      📊 Ingested {len(car_ticks)} telemetry records.")

    print(f"\n      --- Sample Telemetry Ticks for {driver_name} ---")
    for tick in car_ticks[:5]:
        drs_str = f"DRS={tick.drs}" if tick.drs is not None else "DRS=Off/Unavailable"
        print(
            f"      [{tick.date.strftime('%H:%M:%S.%f')[:-3]}] "
            f"Speed: {tick.speed:3d} km/h | Throttle: {tick.throttle:3d}% | "
            f"Brake: {tick.brake:3d}% | Gear: {tick.n_gear} | RPM: {tick.rpm:5d} | {drs_str}"
        )

    # 4. Fetch Interval Data
    print(f"\n[4/4] Ingesting Race Intervals for {driver_name}...")
    intervals = get_intervals(session.session_key, driver_number=target_driver)
    print(f"      ⏱️  Ingested {len(intervals)} interval records.")
    if intervals:
        sample_int = intervals[0]
        print(
            f"      Sample Gap -> Leader: {sample_int.gap_to_leader}s | Interval: {sample_int.interval}s"
        )

    print("\n" + "=" * 60)
    print(" ✅ Telemetry Ingestion Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
