import asyncio
from pitwall_telemetry_engine.ingestion.timeline_replayer import TimelineReplayer


async def main():
    # Run at 10 FPS for readable terminal output (can also test at 30 or 60 FPS)
    replayer = TimelineReplayer(9472, fps=10)
    print("\n" + "=" * 80)
    print("🏎️  LIVE PITWALL TELEMETRY STREAM RUNNING (Press Ctrl+C to stop)")
    print("=" * 80 + "\n")

    try:
        async for frame in replayer.stream_frames(get_selected_drivers_cb=lambda: [1, 55]):
            iso_time = frame["t_sim_iso"].split("T")[1][:8]  # e.g. "15:03:42"
            flag = frame["flag"]
            pct = frame["progress_pct"]

            # Leader position
            positions = frame.get("positions", [])
            p1 = positions[0] if positions else None
            p1_str = f"{p1['acronym']}: ({p1['x']:.0f}, {p1['y']:.0f})" if p1 else "N/A"

            # Telemetry for Verstappen (#1) and Sainz (#55)
            tel = frame.get("telemetry", {})
            t1 = tel.get("1", {})
            t55 = tel.get("55", {})

            ver_stats = f"VER: {t1.get('speed', 0):3d} km/h | G{t1.get('gear', 0)} | THR {t1.get('throttle', 0):3d}% | BRK {t1.get('brake', 0):3d}%"
            sai_stats = f"SAI: {t55.get('speed', 0):3d} km/h | G{t55.get('gear', 0)}"

            battles = frame.get("battles", [])
            battle_str = f"⚔️ Battles: {len(battles)}"
            if battles:
                b0 = battles[0]
                battle_str += f" (#{b0['attacker']} gap: {b0['gap']}s)"

            print(f"[{iso_time}] [{flag:9s}] {pct:5.1f}% | P1 {p1_str:<18s} | {ver_stats} | {battle_str}")

    except KeyboardInterrupt:
        print("\n🛑 Stream stopped by user.")


if __name__ == "__main__":
    asyncio.run(main())
