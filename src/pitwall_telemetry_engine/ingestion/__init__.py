import httpx
from pitwall_telemetry_engine.schemas.driver import Driver
from pitwall_telemetry_engine.schemas.car_data import CarData

BASE_URL = "https://api.openf1.org/v1"

def get_drivers(session_key:str | int = "latest") -> dict[int, Driver]:
    """ Fetches drivers for a session and returns a Driver Registry lookup dictionary """

    url = f"{BASE_URL}/drivers?session_key={session_key}"
    response = httpx.get(url)
    drivers = response.json()
    
    driver_registry = {}
    for d in drivers:
        driver_obj = Driver(**d)
        driver_registry[driver_obj.driver_number] = driver_obj
    
    return driver_registry
    