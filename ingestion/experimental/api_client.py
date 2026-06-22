import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import logging
import os
import time

class APIClient:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def fetch_openweather(self, city: str):
        api_key = os.getenv("OPENWEATHER_API_KEY")
        if not api_key:
            self.logger.warning("OPENWEATHER_API_KEY not set.")
            return None
            
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}"
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch OpenWeather data: {e}")
            return None

    def fetch_coingecko(self, coin_id: str):
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        try:
            # CoinGecko has strict rate limits
            time.sleep(1.5) 
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch CoinGecko data: {e}")
            return None
