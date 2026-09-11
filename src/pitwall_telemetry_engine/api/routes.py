from fastapi import APIRouter, HTTPException
from pitwall_telemetry_engine.ingestion.openf1_client import (
    get_drivers,
    get_latest_race_session,
    get_sessions,
    get_track_geometry,
    get_race_control
)

router = APIRouter(prefix="/api")

@router.get("/session/latest")
def latest_session():
    return get_latest_race_session()

@router.get("/sessions")
def sessions(year: int | None = None):
    return get_sessions(year=year, session_name="Race")

@router.get("/drivers")
def drivers(session_key: str | int = "latest", driver_number: int | None = None):
    registry = get_drivers(session_key)

    if driver_number is not None:
        if driver_number in registry:
            return registry[driver_number]
        raise HTTPException(status_code=404, detail=f"Driver #{driver_number} not found in session")

    return registry

@router.get("/track-geometry")
def track_geometry(session_key: str | int = "latest", sample_driver: int | None = None):
    return get_track_geometry(session_key=session_key, sample_driver=sample_driver)

@router.get("/race-control")
def race_control(session_key: str | int = "latest"):
    return get_race_control(session_key=session_key)
    