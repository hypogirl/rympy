import requests
import re
from datetime import datetime
from typing import List
import json
import bs4
from ratelimit import limits, sleep_and_retry

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
ROOT_URL = "https://rateyourmusic.com"
CALL_LIMIT = 1
RATE_LIMIT = 60

class ParseError(Exception):
    pass

class NoURL(Exception):
    pass

class RequestFailed(Exception):
    pass

class NoContent(Exception):
    pass

class Chart:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, *, chart_type, release_types,
                 year_range=None, primary_genres=None,
                 secondary_genres=None, primary_genres_excluded=None,
                 secondary_genres_excluded=None, locations=None,
                 locations_excluded=None, languages=None,
                 languages_excluded=None, descriptors=None,
                 descriptors_excluded=None, include_subgenres=True,
                 contain_all_genres=False) -> None:
        
        self.type = chart_type
        self.release_types = release_types
        self.year_range = year_range
        self.primary_genres = primary_genres
        self.secondary_genres = secondary_genres
        self.primary_genres_excluded = primary_genres_excluded
        self.secondary_genres_excluded = secondary_genres_excluded
        self.locations = locations
        self.locations_excluded = locations_excluded
        self.languages = languages
        self.languages_excluded = languages_excluded
        self.descriptors = descriptors
        self.descriptors_excluded = descriptors_excluded
        self.include_subgenres = include_subgenres
        self.contain_all_genres = contain_all_genres

        self.init_url = self._fetch_url()
        self.current_url = self.init_url
        self._cached_rym_response = requests.get(self.init_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}.")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.current_page = 1
        self.max_page = self._fetch_max_page()
        if self.current_page > self.max_page:
            raise NoContent("The requested chart has no entries.")
        self.content = self._fetch_entries(init=True)

    def _fetch_url(self):
        url = f"https://rateyourmusic.com/charts/{self.type}/{','.join(self.release_types)}"

        if self.year_range:
            url += f"/{self.year_range.min}-{self.year_range.max}/"

        for field in [(self.primary_genres, self.primary_genres_excluded, "g"),
                        (self.descriptors, self.descriptors_excluded, "d"),
                        (self.secondary_genres, self.secondary_genres_excluded, "s"),
                        (self.languages, self.languages_excluded, "l"),
                        (self.locations, self.locations_excluded, "loc")
                ]:
            if field[2] in ["g", "s"]:
                if field[0]:
                    url += f"/{field[2]}:{','.join([genre.name for genre in field[0]])}"
                    if field[1]:
                        url += f",-{',-'.join([genre._url_name for genre in field[1]])}"
                elif field[1]:
                    url += f"/{field[2]}:-{',-'.join([genre._url_name for genre in field[1]])}"
            else:
                if field[0]:
                    url = f"/d:{','.join(field[0])}"
                    if field[1]:
                        url+= f",-{',-'.join(field[1])}"
                elif field[1]:
                    url+= f"/d:-{',-'.join(field[1])}"

        return url + "/1/"
    
    def _fetch_max_page(self):
        try:
            return int(self._soup.find_all("a", {"class": "ui_pagination_btn ui_pagination_number"})[-1].text)
        except IndexError:
            return 0
        
    def _fetch_entries(self, init=False):
        if self.current_page > self.max_page:
            raise NoContent("No more pages to be loaded.")
        
        if not init:
            self._cached_rym_response = requests.get(self.current_url, headers= headers)
            if self._cached_rym_response.status_code != 200:
                raise RequestFailed(f"Loading next page failed with status code {self._cached_rym_response.status_code}.")
            self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        
        chart_elem = self._soup.find("section", {"id":"page_charts_section_charts"}).contents
        entries = [SimpleRelease(
                        name=(entry.find("div", {"class": "page_charts_section_charts_item_credited_links_primary"})
                            .text.replace("\n", "") +
                            " - " +
                            entry.find("div", {"class": "page_charts_section_charts_item_title"})
                            .text.replace("\n", "")),
                        url=ROOT_URL + entry.contents[1].contents[1]["href"]
                    ) for entry in chart_elem[:-1:2]]
        
        return entries
    
    def load_more_entries(self):
        self.current_page += 1
        self.current_url = re.sub(r"\d+\/$", f"{self.current_page}/", self.current_url)
        self.content += self._fetch_entries()
        return self

    def __str__(self):
        return self._get_representation()

    def __repr__(self):
        return self._get_representation()

    def _get_representation(self):
        return f"Chart: {self.type} {' '.join(self.release_types)}"

class Genre:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url=None, name=None) -> None:
        if not url and not name:
            raise ValueError("At least one of 'url' or 'name' must be provided.")
        if name:
            self._url_name = name.replace(' ', '-').lower()
        else:
            self._url_name = url.split("/")[-2]
        self.url = url or f"https://rateyourmusic.com/genre/{self._url_name}/"
        self._cached_rym_response = requests.get(self.url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.name = self._fetch_name()
        self.akas = self._fetch_akas()
        self.parent_genres = self._fetch_parent_genres()
        self.children_genres = self._fetch_children_genres()

    def top_chart(self, year_range=None):
        return Chart(type=ChartType.top, release_types=[ReleaseType.album], year_range=year_range)
    
    def bottom_chart(self, year_range=None):
        return Chart(type=ChartType.bottom, release_types=[ReleaseType.album], year_range=year_range)
        
    def esoteric_chart(self, year_range=None):
        return Chart(type=ChartType.esoteric, release_types=[ReleaseType.album], year_range=year_range)
        
    def chart(self, *, type=None, year_range=None):
        if not type:
            return Chart(type=ChartType.top, release_types=[ReleaseType.album], year_range=year_range)
        else:
            return Chart(type=type, release_types=[ReleaseType.album], year_range=year_range)


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
        return [SimpleGenre(name= parent.contents[1].contents[1].text, url= ROOT_URL + parent.contents[1].contents[1]["href"]) for parent in parent_elems] or None
    
    def _fetch_children_genres(self):
        genre_elem = self._soup.find("li", {"class":"hierarchy_list_item hierarchy_list_item_current"})
        children_elems = genre_elem.find_next_sibling().contents
        children_genres = list()
        for i in range(1, len(children_elems), 2):
            url = ROOT_URL + children_elems[i].contents[1].contents[1].contents[1]["href"]
            name = children_elems[i].contents[1].contents[1].contents[1].text
            children_genres.append(SimpleGenre(name=name, url=url))
        return children_genres or None

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Genre: {self.name}"
        
class Artist:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url) -> None:
        self._cached_rym_response = requests.get(url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.url = url
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
        
    def _fetch_location(self, date_location_elem):
        if location_elem := date_location_elem.find("a", {"class": "location"}):
            location_list = location_elem.text.split(", ")
            if len(location_list) == 3:
                return Location(city=location_list[0], state=location_list[1], country=location_list[2], url=location_elem["href"])
            elif len(location_list) == 2:
                return Location(state=location_list[0], country=location_list[1], url=location_elem["href"])
            else:
                return Location(country=location_list[0], url=location_elem["href"])

    def _fetch_gen_date_location(self, *titles):
        for title in titles:
            if (date_location_elem := self._soup.find("div", {"class": "info_hdr"}, string=title)):
                date_location_info = date_location_elem.find_next_sibling()
                location = self._fetch_location(date_location_elem)
                date_text = date_location_info.contents[0].strip[:-1]
                date_components_count = date_text.count(" ") + 1
                date_formating = {1: "%Y",
                                2: "%B %Y",
                                3: "%d %B %Y"}
                date = datetime.strptime(date_text, date_formating[date_components_count])
                return {"date": date,
                        "location": location}

    def _fetch_start_date_location(self):
        return self._fetch_gen_date_location("Formed", "Born")

    def _fetch_end_date_location(self):
        return self._fetch_gen_date_location("Disbanded", "Died")
    
    def _fetch_current_location(self):
        return self._fetch_gen_date_location("Currently")["location"] or self.start_date

    def _fetch_genres(self):
        if genre_div := self._soup.find("div", {"class": "info_hdr"}, string="Genres"):
            genres_elem = genre_div.find_next_sibling()
            return [SimpleGenre(name=genre.lstrip()) for genre in genres_elem.text.split(",")]

    def _fetch_members(self):
        if members_div := self._soup.find("div", {"class": "info_hdr"}, string="Members"):
            members_elem = members_div.find_next_sibling()
            members_elems_list = members_elem.contents[0].contents
            members_elems_urls = [member for member in members_elems_list if isinstance(member, bs4.Tag) and member.get("href")]
            members_elem_raw = members_elem.text
            members_name_info = re.findall(r" ?([\w .]+) (?:\[([\w ]+)\] )?\(([\w ,-]+)\)", members_elem_raw)
            members = list()

            urls_index = 0
            for name, aka, info in members_name_info:
                url = None
                if urls_index < len(members_elems_urls) and members_elems_urls[urls_index].text == name:
                    url = ROOT_URL + members_elems_urls[urls_index]["href"]
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
                members.append(BandMember(name=name, instruments=instruments_list, years_active=years_active_list, url=url, aka=aka))
            
            return members

    def _fetch_akas(self):
        if aka_div := self._soup.find("div", {"class": "info_hdr"}, string="Also Known As"):
            aka_elem = aka_div.find_next_sibling()
            akas_text = aka_elem.text.split(",")
            aka_elems_list = aka_elem.contents[0].contents
            aka_elems_urls = [aka for aka in aka_elems_list if isinstance(aka, bs4.Tag) and aka.get("href")]
            akas = list()

            urls_index = 0
            for aka in akas_text:
                url = None
                if urls_index < len(aka_elems_urls) and aka_elems_urls[urls_index].text == aka:
                    url = ROOT_URL + aka_elems_urls[urls_index]["href"]
                    urls_index += 1

                akas.append(SimpleArtist(name=aka, url=url))    

            return akas
        
    def _fetch_notes(self):
        if notes_div := self._soup.find("div", {"class": "info_hdr"}, string="Notes"):
            notes_elem = notes_div.find_next_sibling()
            return notes_elem.text

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Artist: {self.name}"

class Track:
    def __init__(self, *, number, title, length) -> None:
        self.number = number
        self.title = title
        self.length = length

class Release:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url) -> None:
        self._cached_rym_response = requests.get(url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.url = url
        self.title = self._fetch_title()
        self.artists = self._fetch_artists()
        self.average_rating = self._fetch_average_rating()
        self.number_of_ratings = self._fetch_number_of_ratings()
        self.number_of_reviews = self._fetch_number_of_reviews()
        #self._collaboration_symbol = None
        self.release_date = self._fetch_release_date()
        self.recording_date = self._fetch_recording_date()
        self.type = self._fetch_type()
        self.primary_genres = self._fetch_primary_genres()
        self.secondary_genres = self._fetch_secondary_genres()
        self.descriptors = self._fetch_descriptors()
        self.cover_url = self._fetch_cover_url()
        self.links = self._fetch_release_links()
        self.tracks = self._fetch_tracks()
        self.credits = self._fetch_credits()
        self.reviews = None
        self.lists = None
        self._id = self._fetch_id()

    class Lists:
        @sleep_and_retry
        @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
        def __init__(self, url) -> None:
            self.init_url = url
            self.current_url = url
            self._cached_rym_response = requests.get(self.init_url, headers= headers)
            if self._cached_rym_response.status_code != 200:
                raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}.")
            self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
            self.current_page = 1
            self.max_page = self._fetch_max_page()
            if self.current_page > self.max_page:
                raise NoContent("This release has no lists.")
            self.content = self._fetch_lists(init=True)

        def _fetch_max_page(self):
            try:
                return int(self._soup.find_all("a", {"class": "navlinknum"})[-1].text)
            except IndexError:
                return 0

        def _fetch_lists(self, init=False):
            if self.current_page > self.max_page:
                raise NoContent("No more pages to be loaded.")
            
            if not init:
                self._cached_rym_response = requests.get(self.current_url, headers= headers)
                if self._cached_rym_response.status_code != 200:
                    raise RequestFailed(f"Loading next page failed with status code {self._cached_rym_response.status_code}.")
                self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
            
            
            lists_elem = self._soup.find("ul", {"class": "lists expanded"}).contents
            return [SimpleList(
                name= entry.contents[3].contents[1].contents[0].text,
                url= ROOT_URL + entry.contents[3].contents[1].contents[0]["href"]
                ) for entry in lists_elem[1::2]]
        
        def load_more_lists(self):
            self.current_page += 1
            self.current_url = re.sub(r"\d+\/$", f"{self.current_page}/", self.current_url)
            self.content += self._fetch_lists()
            return self


    @property
    def reviews(self):
        return self.reviews or self._fetch_reviews()
    
    @property
    def lists(self):
        return self.lists or self.Lists(self.url + "lists/1/" if self.url.endswith("/") else "/lists/1/")
    

    def _fetch_title(self):
        release_title_elem = self._soup.find("div", {"class": "album_title"})
        try:
            return re.findall(r"(.+)\n +\nBy .+", release_title_elem.text)[0]
        except IndexError:
            raise ParseError("No title was found for this release.")
        
    def _fetch_artists(self):
        outer_elem = self._soup.find("span", {"itemprop":"byArtist"})
        artists_elem = outer_elem.find_all("a", {"class":"artist"})
        return [SimpleArtist(name=artist.text, url=ROOT_URL+artist["href"]) for artist in artists_elem]
    
    def _fetch_average_rating(self):
        if average_rating_elem := self._soup.find("span", {"class": "avg_rating"}):
            return average_rating_elem.text.strip()
        
    def _fetch_number_of_ratings(self):
        if num_ratings_elem := self._soup.find("span", {"class": "num_ratings"}):
            return num_ratings_elem.contents[1].text.strip()
        
    def _fetch_number_of_reviews(self):
        if review_section := self._soup.find("div", {"class": "section_reviews section_outer"}):
            reviews_elem_split = review_section.find("div", {"class": "release_page_header"}).text.split(" ")
            if len(reviews_elem_split) > 1:
                return reviews_elem_split[0]
            
    def _gen_fetch_date(self, regex):
        if date_proto := re.findall(regex, self._soup.text):
            if date := date_proto[0][0] or date_proto[0][1] or date_proto[0][2]:
                date_components_count = date.count(" ") + 1
                date_formating = {1: "%Y",
                                2: "%B %Y",
                                3: "%d %B %Y"}
                return datetime.strptime(date, date_formating[date_components_count])
    
    def _fetch_release_date(self):
        return self._gen_fetch_date(r"Released(\w+ \d+)|Released(\d+ \w+ \d+)|Released(\d{4})")
        
    def _fetch_recording_date(self):
        return self._gen_fetch_date(r"Recorded(\w+ \d+)|Recorded(\d+ \w+ \d+)|Recorded(\d{4})")
            
    def _fetch_type(self):
        if types_proto := re.findall(r"Type((?:\w+, )*\w+)", self._soup.text):
            return types_proto[0].split(",") if "," in types_proto[0] else types_proto[0]

    def _gen_fetch_genres(self, type):
        if genres_elem := self._soup.find("span", {"class": f"release_{type}_genres"}):
            genres_text = genres_elem.text
            return [SimpleGenre(name=genre.lstrip()) for genre in genres_text.split(",")]
    
    def _fetch_primary_genres(self):
        return self._gen_fetch_genres("pri")

    def _fetch_secondary_genres(self):
        return self._gen_fetch_genres("sec")
    
    def _fetch_descriptors(self):
        if descriptors := self._soup.find("span", {"class": "release_pri_descriptors"}):
            return descriptors.text

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

    def _fetch_release_links(self):
        if release_links_elem := self._soup.find("div", {"id": "media_link_button_container_top"}):
            links_json = json.loads(release_links_elem["data-links"])
            release_links = {
                "spotify": None,
                "youtube": None,
                "bandcamp": None,
                "soundcloud": None,
                "applemusic": None
            }
            for platform in links_json:
                match platform:
                    case "spotify":
                        id = next(iter(links_json["spotify"]))
                        release_links["spotify"] = f"https://open.spotify.com/album/{id}"
                    case "youtube":
                        id = next(iter(links_json["youtube"]))
                        release_links["yotube"] = f"https://www.youtube.com/watch?v={id}"
                    case "bandcamp":
                        bandcamp_dict = links_json["bandcamp"]
                        url = [value["url"] for value in bandcamp_dict.values() if value["url"]][0]
                        release_links["bandcamp"] = "https://" + url
                    case "soundcloud":
                        soundcloud_dict = links_json["soundcloud"]
                        url = [value["url"] for value in soundcloud_dict.values() if value["url"]][0]
                        release_links["soundcloud"] = "https://" + url
                    case "applemusic":
                        id = next(iter(links_json["applemusic"]))
                        applemusic_values = links_json["applemusic"].values()
                        (loc, album) = [(value["loc"], value["album"]) for value in applemusic_values][0]
                        release_links["applemusic"] = f"https://music.apple.com/{loc}/album/{album}/{id}"
            return ReleaseLinks(spotify=release_links["spotify"],
                                youtube=release_links["youtube"],
                                bandcamp=release_links["bandcamp"],
                                soundcloud=release_links["soundcloud"],
                                apple_music=release_links["applemusic"])
        
    def _fetch_tracks(self):
        tracks_elem = self._soup.find(id="tracks")
        tracks = list()

        for track in tracks_elem.contents:
            track_number = track.contents[0].find("span", {"class": "tracklist_num"}).text.replace("\n","").replace(" ", "")
            track_title = track.contents[0].find("span", {"class": "tracklist_title"}).text
            track_length = tracks.find("span", {"class": "tracklist_title"}).contents[1]["data-inseconds"]
            tracks.append(Track(number=track_number, title=track_title, length=track_length))
        
        return tracks
    
    def _fetch_credits(self):
        return
        
    def _fetch_reviews(self):
        return
        
    def _fetch_id(self):
        id_elem = self._soup.find("input", {"class": "album_shortcut"})
        try:
            return id_elem["value"][1:-1]
        except TypeError:
            raise ParseError("No ID was found for this release.")

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"{self.type}: {','.join([artist.name for artist in self.artists])} - {self.title}"

    def __eq__(self, other):
        return self.url == other.url
    
class User:
    def __init__(self, *, username=None, url=None) -> None:
        self.username = username or re.search(r"\w+$", url).group()
        if not username:
            raise NoURL("No valid username or URL provided.")
        
class RYMList:
    def __init__(self, url) -> None:
        self.init_url = url
        self.current_url = self.init_url
        self._cached_rym_response = requests.get(self.init_url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.author = self._fetch_author()
        self.content = self._fetch_entries()
        self.current_page = 1
        if not self._soup.find("a", {"class": "navlinknext"}):
            raise NoContent("The requested chart has no entries.")
        self.content = self._fetch_entries(init=True)
        self._id = self._fetch_id()
        
    def _fetch_entries(self, init=False):
        # no clue how to get around with this yet
        '''if not init:
            self._cached_rym_response = requests.get(self.current_url, headers= headers)
            if self._cached_rym_response.status_code != 200:
                raise RequestFailed(f"Loading next page failed with status code {self._cached_rym_response.status_code}.")
            self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        
        if not self._soup.find("a", {"class": "navlinknext"}):
            raise NoContent("No more pages to be loaded.")

        list_elem = self._soup.find("table", {"id":"user_list"}).contents
        entries = [SimpleList() for entry in list_elem[:-1:2]]
        
        return entries'''

    def load_more_entries(self):
        self.current_page += 1
        self.current_url = re.sub(r"\d+\/$", f"{self.current_page}/", self.current_url)
        self.content += self._fetch_entries()
        return self
    
class Review:
    def __init__(self, *, url, release:Release=None) -> None:
        self._cached_rym_response = requests.get(url, headers= headers)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.url = url
        self.content = self._fetch_content()
        self.user = self._fetch_user()
        self.date = self._fetch_date()
        self.release = release or SimpleRelease(name= self._fetch_album_name(), url=self._fetch_release_url())

    def _fetch_content(self):
        return

class Location:
    def __init__(self, *, city=None, state=None, country, url) -> None:
        self.city = city
        self.state = state
        self.country = country
        self.url = url

    def _get_representation(self, init_text):
        full_text = init_text
        if self.city:
            full_text = self.city + ", "
        if self.state:
            full_text += self.state + ", "
        return full_text + self.country
    
    def __str__(self):
        return self._get_representation(str())

    def __repr__(self):
        return self._get_representation("Location: ")
    
class ReleaseLinks:
    def __init__(self, *, spotify=None, youtube=None, bandcamp=None, soundcloud=None, apple_music=None):
        self.spotify = spotify
        self.youtube = youtube
        self.bandcamp = bandcamp
        self.soundcloud = soundcloud
        self.apple_music = apple_music

class SimpleEntity:
    def __init__(self, *, name=None, url=None) -> None:
        self.name = name
        self.url = url

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Simplified: {self.name}"

class SimpleGenre(SimpleEntity):
    def get_genre(self):
        return Genre(self.url, self.name)

class SimpleArtist(SimpleEntity):
    def get_artist(self):
        if self.url:
            return Artist(self.url)
        else:
            raise NoURL("No URL is associated with this artist.")

class SimpleRelease(SimpleEntity):
    def get_release(self):
        return Release(self.url)
    
class SimpleList(SimpleEntity):
    def get_list(self):
        return RYMList(self.url)
    
class BandMember(SimpleArtist):
    def __init__(self, *, name, instruments, years_active, aka, url):
        super().__init__(name=name, url=url)
        self.instruments = instruments
        self.years_active = years_active
        self.aka = aka

class ChartType:
    top = "top"
    bottom = "bottom"
    esoteric = "esoteric"
    diverse = "diverse"
    popular = "popular"

class YearRange:
    def __init__(self, *, min, max) -> None:
        self.min= min
        self.max= max

class ReleaseType:
    album = "album"
    ep = "ep"
    comp = "comp"
    single = "single"
    video = "video"
    unauth = "unauth"
    mixtape = "mixtape"
    musicvideo = "musicvideo"
    djmix = "djmix"
    additional = "addicional"

class Language:
    # ISO 639-1 standard languages
    afrikaans = "af"
    albanian = "sq"
    amharic = "am"
    arabic = "ar"
    armenian = "hy"
    azerbaijani = "az"
    basque = "eu"
    belarusian = "be"
    bengali = "bn"
    bosnian = "bs"
    bulgarian = "bg"
    catalan = "ca"
    cebuano = "ceb"
    chinese = "zh"
    corsican = "co"
    croatian = "hr"
    czech = "cs"
    danish = "da"
    dutch = "nl"
    english = "en"
    esperanto = "eo"
    estonian = "et"
    finnish = "fi"
    french = "fr"
    frisian = "fy"
    galician = "gl"
    georgian = "ka"
    german = "de"
    greek = "el"
    gujarati = "gu"
    haitian_creole = "ht"
    hausa = "ha"
    hawaiian = "haw"
    hebrew = "he"
    hindi = "hi"
    hmong = "hmn"
    hungarian = "hu"
    icelandic = "is"
    igbo = "ig"
    indonesian = "id"
    irish = "ga"
    italian = "it"
    japanese = "ja"
    javanese = "jv"
    kannada = "kn"
    kazakh = "kk"
    khmer = "km"
    kinyarwanda = "rw"
    korean = "ko"
    kurdish = "ku"
    kyrgyz = "ky"
    lao = "lo"
    latin = "la"
    latvian = "lv"
    lithuanian = "lt"
    luxembourgish = "lb"
    macedonian = "mk"
    malagasy = "mg"
    malay = "ms"
    malayalam = "ml"
    maltese = "mt"
    maori = "mi"
    marathi = "mr"
    mongolian = "mn"
    burmese = "my"
    nepali = "ne"
    norwegian = "no"
    pashto = "ps"
    persian = "fa"
    polish = "pl"
    portuguese = "pt"
    punjabi = "pa"
    romanian = "ro"
    russian = "ru"
    samoan = "sm"
    scots_gaelic = "gd"
    serbian = "sr"
    sesotho = "st"
    shona = "sn"
    sindhi = "sd"
    sinhala = "si"
    slovak = "sk"
    slovenian = "sl"
    somali = "so"
    spanish = "es"
    sundanese = "su"
    swahili = "sw"
    swedish = "sv"
    tajik = "tg"
    tamil = "ta"
    telugu = "te"
    thai = "th"
    turkish = "tr"
    ukrainian = "uk"
    urdu = "ur"
    uzbek = "uz"
    vietnamese = "vi"
    welsh = "cy"
    xhosa = "xh"
    yiddish = "yi"
    yoruba = "yo"
    zulu = "zu"