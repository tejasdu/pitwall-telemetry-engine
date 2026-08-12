from pydantic import BaseModel, ConfigDict


class Driver(BaseModel):
    model_config = ConfigDict(extra="ignore")

    driver_number: int
    full_name: str
    name_acronym: str
    session_key: int
    meeting_key: int
    team_name: str | None = None
    team_colour: str | None = None
    headshot_url: str | None = None
