from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Sessions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meeting_key: int
    session_key: int
    session_name: str
    country_name: str
    date_start: datetime
    date_end: datetime
    circuit_short_name: str
    circuit_key: int


    
