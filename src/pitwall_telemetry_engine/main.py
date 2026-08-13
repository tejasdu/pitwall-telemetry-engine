from pitwall_telemetry_engine.ingestion.openf1_client import (
    get_car_data,
    get_drivers,
    get_intervals,
    get_session,
)
from pitwall_telemetry_engine.ingestion.replay import stream_telemetry
import asyncio

async def run_engine() -> None:
    session = get_session("latest")
    car_ticks = get_car_data(session.session_key, driver_number=55)
    print("\n🏎️  STREAMING REPLAY STARTED (5x Speed) — Carlos SAINZ (#55)...\n")
    
    # Stream the first 20 ticks in real-time!
    async for tick in stream_telemetry(car_ticks, playback_factor=10.0):
        print(f"[{tick.date.strftime('%H:%M:%S.%f')[:-3]}] Speed: {tick.speed:3d} km/h | Throttle: {tick.throttle:3d}% | Brake: {tick.brake:3d}%")

def main():
    asyncio.run(run_engine())
    
if __name__ == "__main__":
    main()
