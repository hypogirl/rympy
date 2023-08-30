import requests
import re
from typing import List
from time import sleep
import json
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

class ParseError(Exception):
    pass

class InitialRequestFailed(Exception):
    pass

class Chart:
    def __init__(self, rym_url) -> None:
        sleep(60)
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.elements = None


class Genre:
    def __init__(self, rym_url) -> None:
        sleep(60)
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.name = None
        self.akas = None
        self.parent_genres = None
        self.children_genres = None

class Artist:
    def __init__(self, rym_url) -> None:
        sleep(60)
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.rym_url = rym_url
        self.name = self._fetch_name()
        self.type = self._fetch_type()
        self._start_date_location = self._fetch_start_date_location()
        self.start_date = self._start_date_location['date']
        self.start_location = self._start_date_location['location']
        self.current_location = self._fetch_current_location()
        self._end_date_location = self._fetch_end_date_location()
        self.end_date = self._end_date_location['date']
        self.end_location = self._end_date_location['location']
        self.genres = self._fetch_genres()
        self.members = self._fetch_members()
        self.akas = self._fetch_akas()

    @property
    def birth_date(self):
        return self.start_date
    
    @property
    def formation_date(self):
        return self.start_date

    @property
    def death_date(self):
        return self.end_date
    
    @property
    def disbanded_date(self):
        return self.end_date

    def _fetch_name(self):
        try:
            return self._soup.find("h1", {"class": "artist_name_hdr"}).text
        except AttributeError:
            raise ParseError("No artist name was found.")

    def _fetch_type(self):
        # Fetch and return the artist's type (individual, band, etc.)
        pass

    def _fetch_start_date_location(self):
        return self._fetch_gen_date_location("Formed", "Born")

    def _fetch_end_date_location(self):
        return self._fetch_gen_date_location("Disbanded", "Died")
    
    def _fetch_current_location(self):
        return self._fetch_gen_date_location("Currently") or self.start_date

    def _fetch_gen_date_location(self, *titles):
        for title in titles:
            if (gen_elem := self._soup.find("div", {"class": "info_hdr"}, string=title)):
                gen_info = gen_elem.find_next_sibling().text.split(",")
                return {
                    'date': gen_info[0].lstrip(),
                    'location': [location_info.lstrip() for location_info in gen_info[1:]]
                }
        return {
            'date': None,
            'location': None
        }

    def _fetch_genres(self):
        try:
            genre_div = self._soup.find("div", {"class": "info_hdr"}, string="Genres")
            genres_elem = genre_div.find_next_sibling()
        except:
            return None
        else:
            return genres_elem.text

    def _fetch_members(self):
        try:
            members_div = self._soup.find("div", {"class": "info_hdr"}, string="Members")
            members_elem = members_div.find_next_sibling()
        except:
            return None
        else:
            members_elems_list = list(list(members_elem.children)[0].children)
            members_elems_urls = [member.get("href") for member in members_elems_list if member.get("href")]
            members_elem_raw = members_elem.text
            members_name_info = re.findall(r" ?([\w .]+) (?:\[[\w ]+\] )?\(([\w ,-]+)\)", members_elem_raw)
            members_instrument = {}

            urls_index = 0
            for name, info in members_name_info:
                url = None
                if urls_index < len(members_elems_urls) and members_elems_urls[urls_index].text == name:
                    url = "https://rateyourmusic.com" + members_elems_urls[urls_index]["href"]
                    urls_index += 1
                
                instruments_list = list()
                years_active_list = list()
                for instrument, period in re.findall(r"([a-zA-Z][a-zA-Z ]+)| ?(\d+(?:-\d+))", info):
                    if instrument:
                        instruments_list.append(instrument)
                    elif period:
                        years_active_list.append(period)
                
                members_instrument[name] = {
                    "instruments": instruments_list,
                    "years_active": years_active_list,
                    "url": url
                }


    def _fetch_akas(self):
        # Fetch and return the artist's known aliases or alternative names
        pass

class Release:
    def __init__(self, rym_url) -> None:
        sleep(60)
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.rym_url = rym_url        
        self.title = self._fetch_title()
        self.artists = self._fetch_artists()
        self._collaboration_symbol = None
        self.year = self._fetch_year()
        self.type = self._fetch_type()
        self.primary_genres = self._fetch_primary_genres()
        self.secondary_genres = self._fetch_secondary_genres()
        self.descriptors = self._fetch_descriptors()
        self.cover_url = self._fetch_cover_url()
        self._id = self._fetch_id()

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
    
    def _fetch_type(self):
        return re.findall("Type(\w+)", self._soup.text)[0]
    
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
    
    def _fetch_descriptors(self):
        try:
            descriptors = self._soup.find("span", {"class": "release_pri_descriptors"}).text
        except:
            descriptors = None
        return descriptors

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
    
    def _fetch_id(self):
        id_elem = self._soup.find("input", {"class": "album_shortcut"})
        try:
            return id_elem["value"][1:-1]
        except TypeError:
            raise ParseError("No ID was found for this release.")

    def __str__(self):
        return f"{self.artists} - {self.title}"

    def __eq__(self, other):
        return self.rym_url == other.rym_url
    
class SimpleEntity:
    def __init__(self, *, name, rym_url) -> None:
        self.name = name
        self.url = rym_url

class SimpleArtist(SimpleEntity):
    def get_artist(self):
        return Artist(self.url)

class SimpleRelease(SimpleEntity):
    def get_release(self):
        return Release(self.url)