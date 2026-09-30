from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Laps(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_key: int
    meeting_key: int
    driver_number: int
    lap_number: int
    date_start: datetime | None = None
    lap_duration: float | None = None
    duration_sector_1: float | None = None
    duration_sector_2: float | None = None
    duration_sector_3: float | None = None
    i1_speed: float | None = None
    i2_speed: float | None = None
    st_speed: float | None = None
    is_pit_out_lap: bool = False
    segments_sector_1: list[int | None] | None = None
    segments_sector_2: list[int | None] | None = None
    segments_sector_3: list[int | None] | None = None
