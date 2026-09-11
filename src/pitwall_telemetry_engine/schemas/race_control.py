from datetime import datetime
from pydantic import BaseModel, ConfigDict


class RaceControlMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_key: int
    date: datetime
    category: str | None = None
    flag: str | None = None
    message: str | None = None
    scope: str | None = None
    sector: int | None = None
    driver_number: int | None = None
