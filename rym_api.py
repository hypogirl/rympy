import requests
import re
from typing import List
from time import sleep
import json
import bs4
from ratelimit import limits, sleep_and_retry

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
RATE_LIMIT = 60

class ParseError(Exception):
    pass

class NoURL(Exception):
    pass

class InitialRequestFailed(Exception):
    pass

class Chart:
    @sleep_and_retry
    @limits(calls=RATE_LIMIT)
    def __init__(self, rym_url) -> None:
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.elements = None


class Genre:
    @sleep_and_retry
    @limits(calls=RATE_LIMIT)
    def __init__(self, rym_url=None, name=None) -> None:
        if not(rym_url) and not(name):
            raise ValueError("At least one of 'rym_url' or 'name' must be provided.")
        
        self.url = rym_url or f"https://rateyourmusic.com/genre/{name.replace(' ', '-').lower()}/"
        self._cached_rym_response = requests.get(self.url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.name = name or self._fetch_name()
        self.akas = self._fetch_akas()
        self.parent_genres = self._fetch_parent_genres()
        self.children_genres = self._fetch_children_genres()

    def _fetch_name(self):
        try:
            return self._soup.find("section", {"id": "page_genre_section_name"}).contents[1].text
        except AttributeError:
            raise ParseError("No genre name was found.")
        
    def _fetch_akas(self):
        if aka_elems := self._soup.find_all("bdi", class_="comma_separated"):
            return [aka.text for aka in aka_elems]
        
    def _fetch_parent_genres(self):
        parent_elems = self._soup.find_all("li", {"class":"hierarchy_list_item parent"})
        return [Genre(rym_url= "https://rateyourmusic.com" + parent.contents[1].contents[1]["href"], name= parent.contents[1].contents[1].text) for parent in parent_elems]
    
    def _fetch_children_genres(self):
        genre_elem = self._soup.find("li", {"class":"hierarchy_list_item hierarchy_list_item_current"})
        children_elems = genre_elem.find_next_sibling().contents
        children_genres = list()
        for i in range(1, len(children_elems), 2):
            url = "https://rateyourmusic.com" + children_elems[i].contents[1].contents[1].contents[1]["href"]
            name = children_elems[i].contents[1].contents[1].contents[1].text
            children_genres.append(Genre(rym_url=url, name= name))
        return children_genres
        



class Artist:
    @sleep_and_retry
    @limits(calls=RATE_LIMIT)
    def __init__(self, rym_url) -> None:
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.rym_url = rym_url
        self.name = self._fetch_name()
        #self.type = self._fetch_type()
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
        self.notes = self._fetch_notes()

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
            members_elems_list = members_elem.contents[0].contents
            members_elems_urls = [member for member in members_elems_list if isinstance(member, bs4.Tag) and member.get("href")]
            members_elem_raw = members_elem.text
            members_name_info = re.findall(r" ?([\w .]+) (?:\[([\w ]+)\] )?\(([\w ,-]+)\)", members_elem_raw)
            members = list()

            urls_index = 0
            for name, aka, info in members_name_info:
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
                
                instruments_list = instruments_list or None
                years_active_list = years_active_list or None
                aka = aka or None
                members.append(BandMember(name=name, instruments=instruments_list, years_active=years_active_list, rym_url=url, aka=aka))
            
            return members

    def _fetch_akas(self):
        try:
            aka_div = self._soup.find("div", {"class": "info_hdr"}, string="Also Known As")
            aka_elem = aka_div.find_next_sibling()
        except:
            return None
        else:
            akas_text = aka_elem.text.split(",")
            aka_elems_list = aka_elem.contents[0].contents
            aka_elems_urls = [aka for aka in aka_elems_list if isinstance(aka, bs4.Tag) and aka.get("href")]
            akas = list()

            urls_index = 0
            for aka in akas_text:
                url = None
                if urls_index < len(aka_elems_urls) and aka_elems_urls[urls_index].text == aka:
                    url = "https://rateyourmusic.com" + aka_elems_urls[urls_index]["href"]
                    urls_index += 1

                akas.append(SimpleArtist(name=aka, rym_url=url))    

            return akas
        
    def _fetch_notes(self):
        try:
            notes_div = self._soup.find("div", {"class": "info_hdr"}, string="Notes")
            notes_elem = notes_div.find_next_sibling()
        except:
            return None
        else:
            return notes_elem.text


class Release:
    def __init__(self, rym_url) -> None:
        sleep(60)
        self._cached_rym_response = requests.get(rym_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise InitialRequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
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
            artist_name = release_title_elem.find("span", {"class": "credited_name"}).contents[0] # this only works for collaborative albums
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
        if self.url:
            return Artist(self.url)
        else:
            raise NoURL("No URL is associated with this artist.")

class SimpleRelease(SimpleEntity):
    def get_release(self):
        return Release(self.url)
    
class BandMember(SimpleArtist):
    def __init__(self, *, name, instruments, years_active, aka, rym_url):
        super().__init__(name=name, rym_url=rym_url)
        self.instruments = instruments
        self.years_active = years_active
        self.aka = aka

    def get_artist(self):
        if self.url:
            return Artist(self.url)
        else:
            raise NoURL("No URL is associated with this artist.")