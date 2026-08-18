from pydantic import BaseModel, ConfigDict

class Driver(BaseModel):
    model_config = ConfigDict(extra="ignore")

    driver_number: int
    full_name: str
    name_acronym: str
    headshot_url: str | None = None
    session_key: int
    meeting_key: int
    team_name: str
    team_colour: str | None = None 
    

    
