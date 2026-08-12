from datetime import datetime
from pydantic import BaseModel, ConfigDict


class Intervals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: datetime
    driver_number: int
    meeting_key: int
    session_key: int
    interval: float | str | None = None  # e.g., 0.452, "+1 LAP", or None
    gap_to_leader: float | str | None = None  # e.g., 12.341, "+1 LAP", or None