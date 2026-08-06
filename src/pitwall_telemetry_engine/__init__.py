import requests
from requests.exceptions import HTTPError
import json
import pandas as pd
from urllib.request import urlopen

def main() -> None:

    response = urlopen('https://api.openf1.org/v1/car_data?driver_number=55&session_key=9159&speed>=315')
    data = json.loads(response.read().decode('utf-8'))
    
    #with open('car_data.json', 'w') as f:
    #    json.dump(data, f, indent=4)


if __name__ == "__main__":
    main()