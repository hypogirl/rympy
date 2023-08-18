import requests
import re
from time import sleep
import json
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

class ParseError(Exception):
    pass

class InitialRequestFailed(Exception):
    pass

class Artist:
    pass

class Genre:
    pass

class Release:
    def __init__(self, rym_url) -> None:
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        sleep(60)
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
        try:
            return re.findall(r".+\n +\nBy (.+)", release_title_elem.text)[0]
        except IndexError:
            raise ParseError("No title was found for this release.")
        
    def _fetch_artists(self):
        release_title_elem = self._soup.find("div", {"class": "album_title"})
        try:
            artist_name = list(release_title_elem.find("span", {"class": "credited_name"}).children)[0] # this only works for collaborative albums
        except:
            artist_name = re.findall(".+\n +\nBy (.+)", release_title_elem.text)[0]
        return artist_name
    
    def _fetch_year(self):
        release_year_proto = re.findall(r"Released\w+ (\d+)|Released\d+ \w+ (\d+)|Released(\d{4})", self._soup.text)
        if release_year_proto:
            release_year = release_year_proto[0][0] or release_year_proto[0][1] or release_year_proto[0][2]
        else:
            release_year = None
        return release_year
    
    def _fetch_primary_genres(self):
        try:
            primary_genres = self._soup.find("span", {"class": "release_pri_genres"}).text
        except:
            primary_genres = None
        return primary_genres

    def _fetch_secondary_genres(self):
        try:
            secondary_genres = self._soup.find("span", {"class": "release_sec_genres"}).text
        except:
            secondary_genres = None
        return secondary_genres

    def _fetch_cover_url(self):
        release_cover_elem = self._soup.find("img")
        try:
            if release_cover_elem["alt"].startswith("Cover art for ") and "https://e.snmc.io/3.0/img/blocked_art/enable_img_600x600.png" not in release_cover_elem["src"]:
                release_cover_url = "https:" + release_cover_elem["src"]
            else:
                release_cover_url = None
        except KeyError:
            release_cover_url = None
        return release_cover_url

    def _fetch_release_type(self):
        release_type = re.findall("Type(\w+)", self._soup.text)[0]
        return release_type

    def _fetch_release_links(self):
        release_links_elem = self._soup.find("div", {"id": "media_link_button_container_top"})
        if release_links_elem:
            release_links = json.loads(release_links_elem["data-links"])
        else:
            release_links = None
        return release_links
    
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
    
    def get_primary_genres(self):
        if self._primary_genres:
            return self._primary_genres
        
        self._primary_genres = self._fetch_primary_genres()
        return self._primary_genres

    def get_secondary_genres(self):
        if self._secondary_genres:
            return self._secondary_genres
        
        self._secondary_genres = self._fetch_secondary_genres()
        return self._secondary_genres

    def get_cover_url(self):
        if self._cover_url:
            return self._cover_url
        
        self._cover_url = self._fetch_cover_url()
        return self._cover_url

    def get_release_type(self):
        if self._type:
            return self._type
        
        self._type = self._fetch_release_type()
        return self._type

    def get_release_links(self):
        if self._release_links:
            return self._release_links
        
        self._release_links = self._fetch_release_links()
        return self._release_links

    def __str__(self):
        return f"{self.get_artists()} - {self.get_title()} ({self.get_year()})"

    def __eq__(self, other):
        return self.rym_url == other.rym_url