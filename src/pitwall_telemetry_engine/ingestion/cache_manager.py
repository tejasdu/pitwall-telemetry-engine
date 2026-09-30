"""Cache Manager CLI & Utility for Pitwall Telemetry Engine.

Provides automated pre-caching, validation, repair, and deletion
for OpenF1 race session datasets on disk.
"""

import argparse
import shutil
import sys
import time
from datetime import datetime, timezone

from pitwall_telemetry_engine.ingestion.openf1_client import (
    CACHE_DIR,
    get_car_data,
    get_drivers,
    get_intervals,
    get_laps,
    get_location,
    get_pit,
    get_position,
    get_race_control,
    get_session,
    get_sessions,
    get_stints,
    get_track_geometry,
)


def audit_session(session_key: str | int) -> dict:
    """Audits the completeness of a cached session on disk."""
    key = str(session_key)
    session_dir = CACHE_DIR / key

    if not session_dir.exists() or not session_dir.is_dir():
        return {
            "session_key": key,
            "exists": False,
            "is_complete": False,
            "status": "NOT_CACHED",
            "drivers_count": 0,
            "car_data_count": 0,
            "location_count": 0,
            "missing": ["directory_missing"],
        }

    missing = []
    required_files = [
        "sessions.json",
        "drivers.json",
        "intervals.json",
        "laps.json",
        "pit.json",
        "position.json",
        "race_control.json",
        "stints.json",
        "track_geometry.json",
    ]

    for f in required_files:
        fp = session_dir / f
        if not fp.exists() or fp.stat().st_size < 2:
            missing.append(f)

    # Check drivers
    drivers_file = session_dir / "drivers.json"
    driver_count = 0
    if drivers_file.exists() and drivers_file.stat().st_size > 10:
        try:
            import json

            data = json.loads(drivers_file.read_text(encoding="utf-8"))
            driver_count = len(data) if isinstance(data, list) else len(data.keys())
        except Exception:
            driver_count = 0

    car_data_dir = session_dir / "car_data"
    car_count = 0
    if car_data_dir.exists() and car_data_dir.is_dir():
        car_count = len(
            [f for f in car_data_dir.iterdir() if f.is_file() and f.stat().st_size > 100]
        )

    loc_dir = session_dir / "location"
    loc_count = 0
    if loc_dir.exists() and loc_dir.is_dir():
        loc_count = len([f for f in loc_dir.iterdir() if f.is_file() and f.stat().st_size > 100])

    is_complete = (
        len(missing) == 0
        and driver_count > 0
        and car_count >= driver_count - 2
        and loc_count >= driver_count - 2
    )

    if not is_complete:
        if car_count == 0 and loc_count == 0:
            status = "EMPTY_OR_CORRUPT"
        else:
            status = "PARTIAL"
    else:
        status = "COMPLETE"

    return {
        "session_key": key,
        "exists": True,
        "is_complete": is_complete,
        "status": status,
        "drivers_count": driver_count,
        "car_data_count": car_count,
        "location_count": loc_count,
        "missing": missing,
    }


def audit_all() -> None:
    """Prints a formatted report of all cached sessions."""
    if not CACHE_DIR.exists():
        print(f"⚠️ Cache directory does not exist: {CACHE_DIR}")
        return

    sessions = [d for d in CACHE_DIR.iterdir() if d.is_dir() and d.name.isdigit()]
    if not sessions:
        print("ℹ️ No cached sessions found in storage.")
        return

    print("=" * 80)
    print(
        f"{'SESSION':<10} | {'STATUS':<18} | {'DRIVERS':<8} | {'CAR DATA':<9} | {'LOCATIONS':<9} | {'MISSING'}"
    )
    print("-" * 80)

    for s in sorted(sessions, key=lambda p: int(p.name)):
        report = audit_session(s.name)
        status_icon = (
            "✅ COMPLETE"
            if report["status"] == "COMPLETE"
            else ("⚠️ PARTIAL" if report["status"] == "PARTIAL" else "❌ CORRUPT")
        )
        missing_str = ", ".join(report["missing"]) if report["missing"] else "None"
        print(
            f"{report['session_key']:<10} | {status_icon:<18} | {report['drivers_count']:<8} | "
            f"{report['car_data_count']:<9} | {report['location_count']:<9} | {missing_str}"
        )
    print("=" * 80)


def delete_session(session_key: str | int) -> bool:
    """Deletes a session directory from the cache."""
    key = str(session_key)
    session_dir = CACHE_DIR / key
    if session_dir.exists():
        shutil.rmtree(session_dir)
        print(f"🗑️ Deleted cache directory for session {key}")
        return True
    else:
        print(f"ℹ️ Session directory {key} does not exist.")
        return False


def prewarm_session(session_key: str | int, force: bool = False) -> bool:
    """Pre-caches all telemetry, intervals, track geometry, and coordinates for a race."""
    key = int(session_key)

    # Skip immediately if session is already complete on disk
    if not force:
        audit = audit_session(key)
        if audit["is_complete"]:
            print(f"⏩ [Skip] Session {key} is already 100% COMPLETE in cache.")
            return True

    print(f"\n🚀 [Pitwall Cache Manager] Pre-warming session {key}...")
    start_time = time.perf_counter()

    try:
        # 1. Metadata
        print("  • Fetching session metadata...")
        session = get_session(key)
        print(
            f"    🏁 Grand Prix: {session.country_name} ({session.circuit_short_name} {session.year})"
        )

        # 2. Drivers
        print("  • Fetching driver registry...")
        drivers = get_drivers(key)
        driver_numbers = sorted(list(drivers.keys()))
        print(f"    🏎️ Found {len(driver_numbers)} drivers: {driver_numbers}")

        if not driver_numbers:
            print("  ❌ No drivers found for this session. Aborting.")
            return False

        # 3. Macro timing feeds
        print("  • Ingesting timing intervals, race control flags, pits, and laps...")
        get_intervals(key)
        get_position(key)
        get_race_control(key)
        get_pit(key)
        get_laps(key)
        get_stints(key)

        # 4. Driver Telemetry & GPS Coordinates (with gentle throttling to prevent 429s)
        print("  • Downloading high-frequency car telemetry & GPS locations...")
        for idx, d_num in enumerate(driver_numbers, start=1):
            drv = drivers[d_num]
            tag = f"{drv.name_acronym} (#{d_num})"

            car_path = CACHE_DIR / str(key) / "car_data" / f"{d_num}.json"
            loc_path = CACHE_DIR / str(key) / "location" / f"{d_num}.json"

            need_car = force or not car_path.exists() or car_path.stat().st_size < 100
            need_loc = force or not loc_path.exists() or loc_path.stat().st_size < 100

            if need_car:
                sys.stdout.write(f"    [{idx}/{len(driver_numbers)}] {tag} car_data... ")
                sys.stdout.flush()
                get_car_data(key, driver_number=d_num)
                print("done")
                time.sleep(0.25)  # Polite sleep to respect OpenF1 rate limits

            if need_loc:
                sys.stdout.write(f"    [{idx}/{len(driver_numbers)}] {tag} location... ")
                sys.stdout.flush()
                get_location(key, driver_number=d_num)
                print("done")
                time.sleep(0.25)

        # 5. Track Geometry (generates spline from cached locations)
        print("  • Generating Catmull-Rom track geometry spline...")
        get_track_geometry(key)

        elapsed = time.perf_counter() - start_time
        print(f"✅ Session {key} successfully pre-warmed and verified in {elapsed:.1f}s!\n")
        return True

    except Exception as e:
        print(f"❌ Error pre-warming session {key}: {e}")
        return False


def prewarm_year(year: int, force: bool = False) -> None:
    """Pre-warms all completed race sessions for an entire championship season."""
    print(f"\n🏎️ [Pitwall Cache Manager] Ingesting all completed races for {year} season...")
    all_sessions = get_sessions(year=year, session_name="Race")

    now = datetime.now(timezone.utc)
    completed_sessions = [
        s
        for s in all_sessions
        if s.date_start
        and s.date_start <= now
        and not getattr(s, "is_cancelled", False)
        and not (s.year == 2023 and (s.session_key == 9086 or s.circuit_short_name == "Imola"))
    ]

    # Sort oldest to newest
    completed_sessions.sort(key=lambda s: s.date_start)
    print(f"Found {len(completed_sessions)} completed races in {year}.\n")

    for idx, s in enumerate(completed_sessions, start=1):
        print(
            f"=== [{idx}/{len(completed_sessions)}] {s.country_name} GP ({s.circuit_short_name}) - Key {s.session_key} ==="
        )
        prewarm_session(s.session_key, force=force)
        time.sleep(2.0)


def prewarm_all(force: bool = False) -> None:
    """Pre-warms all completed race sessions across all supported championship seasons."""
    print("\n🌍 [Pitwall Cache Manager] Pre-warming ALL completed races from 2023 to 2026...")
    for y in [2026, 2025, 2024, 2023]:
        prewarm_year(y, force=force)


def main():
    parser = argparse.ArgumentParser(description="Pitwall Telemetry Cache Manager")
    parser.add_argument(
        "session_key", nargs="?", type=str, help="Session key to cache (e.g. 11369 or 11377)"
    )
    parser.add_argument(
        "--year", type=int, help="Pre-cache all completed races for a year (e.g. 2024)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Pre-cache all completed races across all supported seasons (2023-2026)",
    )
    parser.add_argument("--audit", action="store_true", help="Audit all cached sessions on disk")
    parser.add_argument(
        "--delete", type=str, help="Delete a specific session cache directory (e.g. 9159)"
    )
    parser.add_argument(
        "--clean-corrupted", action="store_true", help="Delete all corrupt or empty sessions"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-download even if already cached"
    )

    args = parser.parse_args()

    if args.audit:
        audit_all()
        return

    if args.clean_corrupted:
        if not CACHE_DIR.exists():
            return
        for s in CACHE_DIR.iterdir():
            if s.is_dir() and s.name.isdigit():
                report = audit_session(s.name)
                if report["status"] == "EMPTY_OR_CORRUPT":
                    delete_session(s.name)
        return

    if args.delete:
        delete_session(args.delete)
        return

    if args.all:
        prewarm_all(force=args.force)
        return

    if args.year:
        prewarm_year(args.year, force=args.force)
        return

    if args.session_key:
        prewarm_session(args.session_key, force=args.force)
        return

    # Default action if no flags passed: show audit
    audit_all()


if __name__ == "__main__":
    main()
