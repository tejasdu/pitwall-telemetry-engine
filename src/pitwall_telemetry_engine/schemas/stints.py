from pydantic import BaseModel, ConfigDict


class Stints(BaseModel):
    model_config = ConfigDict(extra="ignore")

    driver_number: int
    stint_number: int
    session_key: int
    meeting_key: int
    compound: str | None = None
    fresh_tyres: bool = False
    lap_start: int
    lap_end: int | None = None
    stint_duration: float | None = None
    tyre_age_at_start: int | None = 0
