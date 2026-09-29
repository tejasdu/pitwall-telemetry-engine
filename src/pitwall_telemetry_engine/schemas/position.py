from datetime import datetime
from pydantic import BaseModel, ConfigDict

class Position(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: datetime
    driver_number: int
    meeting_key: int
    session_key: int
    position: int
