import requests
from requests.exceptions import HTTPError
import json
import pandas as pd
from urllib.request import urlopen
from .schemas.car_data import CarData

def main() -> None:
    file_path = "car_data.json"

    with open(file_path, "r") as f:
        raw_data = json.load(f)
    
    print(f"Loaded {len(raw_data)} records:\n")
    for record in raw_data:
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