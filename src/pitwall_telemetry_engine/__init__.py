import requests
from requests.exceptions import HTTPError
import json
import pandas as pd
from urllib.request import urlopen
from .schemas.car_data import CarData
import httpx

def main() -> None:
    url = "https://api.openf1.org/v1/car_data?session_key=latest&driver_number=55"
    response = httpx.get(url)
    raw_data = response.json() 
    # print(raw_data)

    #file_path = "driver_data.json"
    #with open(file_path, "w", encoding="utf-8") as f:
    #    json.dump(raw_data, f, indent=2)

    print(f"Loaded {len(raw_data)} records:\n")

    for record in raw_data[:5]:
       telemetry_data = CarData(**record)
       
       print(f"{telemetry_data.date}")
       print(f"{telemetry_data.brake}")
       print(f"{telemetry_data.driver_number}")
       print(f"{telemetry_data.drs}")
       print(f"{telemetry_data.meeting_key}")
       print(f"{telemetry_data.session_key}")
       print(f"{telemetry_data.n_gear}")
       print(f"{telemetry_data.rpm}")
       print(f"{telemetry_data.speed}")
       print(f"{telemetry_data.throttle}")
       print("\n")


if __name__ == "__main__":
    main()