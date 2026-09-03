from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Location(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_key: int
    meeting_key: int
    driver_number: int
    date: datetime
    x: float
    y: float
    z: float


    