from datetime import datetime
from pydantic import BaseModel, ConfigDict

class Pit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: datetime
    driver_number: int
    meeting_key: int
    session_key: int
    pit_duration: float | None = None
    lane_duration: float | None = None
    stop_duration: float | None = None
    lap_number: int | None = None
