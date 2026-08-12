from datetime import datetime
from pydantic import BaseModel, ConfigDict

class CarData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: datetime
    brake: int
    driver_number: int
    drs: int | None = None
    meeting_key: int
    session_key: int
    n_gear: int
    rpm: int
    speed: int
    throttle: int





    