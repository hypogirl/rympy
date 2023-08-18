import requests
import re
import asyncio
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

class InitialRequestFailed(Exception):
    pass

class Artist:
    pass

class Artists:
    pass

class Release:
    def __init__(self, rym_url) -> None:
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        
        self._soup = BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.rym_url = rym_url        
        self._title = None
        self._artists = None
        self._year = None
        self._type = None
        self._primary_genres = None
        self._secondary_genres = None
        self._cover_url = None

    def _fetch_title(self):
        release_title_elem = self._soup.find("div", {"class": "album_title"})
        return re.findall(r".+\n +\nBy (.+)", release_title_elem.text)[0]
    
    def _fetch_year(self):
        release_year_proto = re.findall(r"Released\w+ (\d+)|Released\d+ \w+ (\d+)|Released(\d{4})", self._soup.text)
        if release_year_proto:
            release_year = release_year_proto[0][0] or release_year_proto[0][1] or release_year_proto[0][2]
        else:
            release_year = None
        
        return release_year
    
    def get_title(self):
        if self._title:
            return self._title
        
        self._title = self._fetch_title()
        return self._title
    
    def get_year(self):
        if self._year:
            return self._year
        
        self._year = self._fetch_year()
        return self._year