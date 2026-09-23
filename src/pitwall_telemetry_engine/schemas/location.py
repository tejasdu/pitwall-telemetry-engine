from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Location(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_key: int
    meeting_key: int | None = None
    driver_number: int
    date: datetime
    x: float
    y: float
    z: float
