import asyncio
from typing import AsyncGenerator
from pitwall_telemetry_engine.schemas.car_data import CarData
from datetime import datetime

# List of telemetry ticks for streaming

async def stream_telemetry(
    car_ticks: list[CarData], 
    playback_factor: float = 1.0,
    max_pause_seconds: float = 2.0
) -> AsyncGenerator[CarData, None]:
    
    if not car_ticks:
        return 
    
    #Immediately yield the first tick
    yield car_ticks[0]

    for i in range(len(car_ticks) - 1):
        curr_tick = car_ticks[i]
        next_tick = car_ticks[i + 1]

        # 1. Calculate time difference between ticks in seconds
        time_diff = (next_tick.date - curr_tick.date).total_seconds()

        #If a flag on play/pause in session, skip to next tick
        if time_diff > max_pause_seconds:
            pause_minutes = time_diff / 60.0

            print(
                f"\n ⚠️  [SESSION PAUSE DETECTED] Gap of {pause_minutes:.1f} mins between "
                f"{curr_tick.date.strftime('%H:%M:%S')} and {next_tick.date.strftime('%H:%M:%S')}. "
                f"Fast-forwarding to next tick in 5 seconds... \n"
            )

            await asyncio.sleep(5.0)
            capped_diff = 0.0
        else:
            # 2. Saftey cap to make sure time diff isn't more than max pause allowed
            capped_diff = max(time_diff, 0.0)

        # 3. Sleep duration based on user playback speed selected
        sleep_duration = capped_diff / playback_factor

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)    
        
        # 4. Yield next telemetry tick
        yield next_tick    
        
        

        