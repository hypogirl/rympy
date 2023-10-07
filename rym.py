import requests
import re
from datetime import datetime
from datetime import timedelta
from typing import List
import json
import bs4
from ratelimit import limits, sleep_and_retry

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
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
        self._cached_rym_response = requests.get(self.init_url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}.")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.current_page = 1
        self.max_page = self._fetch_max_page()
        if self.current_page > self.max_page:
            raise NoContent("The requested chart has no entries.")
        self.content = self._fetch_entries(init=True)

    def _fetch_url(self):
        release_types_str = str()
        if isinstance(self.release_types, list):
            release_types_str = ','.join(self.release_types)
       
        url = f"https://rateyourmusic.com/charts/{self.type}/{release_types_str or self.release_types}"

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
            return int(self._soup.find_all("a", class_= "ui_pagination_btn ui_pagination_number")[-1].text)
        except IndexError:
            return 0
        
    def _fetch_entries(self, init=False):
        if self.current_page > self.max_page:
            raise NoContent("No more pages to be loaded.")
        
        if not init:
            self._cached_rym_response = requests.get(self.current_url, headers= HEADERS)
            if self._cached_rym_response.status_code != 200:
                raise RequestFailed(f"Loading next page failed with status code {self._cached_rym_response.status_code}.")
            self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        
        chart_elem = self._soup.find("section", id="page_charts_section_charts").contents
        entries = [SimpleRelease(
                        title=(entry.find("div", class_= "page_charts_section_charts_item_credited_links_primary")
                            .text.replace("\n", "") +
                            " - " +
                            entry.find("div", class_= "page_charts_section_charts_item_title")
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
        self._cached_rym_response = requests.get(self.url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.name = self._fetch_name()
        self.short_description = self._fetch_short_description()
        self.description = self._fetch_description()
        self.akas = self._fetch_akas()
        self.parent_genres = self._fetch_parent_genres()
        self.children_genres = self._fetch_children_genres()
        self._top_chart = None
        self._bottom_chart = None
        self._esoteric_chart = None
        self.top_ten_albums = self._fetch_top_ten()

    @property
    def top_chart(self):
        if not self._top_chart:
            self._top_chart = Chart(type=ChartType.top, release_types=ReleaseType.album)
        return self._top_chart

    @property
    def bottom_chart(self):
        if not self._bottom_chart:
            self._bottom_chart = Chart(type=ChartType.bottom, release_types=ReleaseType.album)
        return self._bottom_chart
    
    @property
    def esoteric_chart(self):
        if not self._esoteric_chart:
            self._esoteric_chart = Chart(type=ChartType.esoteric, release_types=ReleaseType.album)
        return self._esoteric_chart
        
    def chart(self, *, type=None, year_range=None):
        if not type:
            return Chart(type=ChartType.top, release_types=ReleaseType.album, year_range=year_range)
        else:
            return Chart(type=type, release_types=ReleaseType.album, year_range=year_range)


    def _fetch_name(self):
        try:
            return self._soup.find("section", id="page_genre_section_name").contents[1].text
        except AttributeError:
            raise ParseError("No genre name was found.")
        
    def _fetch_short_description(self):
        return self._soup.find(id="page_genre_description_short").text
        
    def _fetch_description(self):
        return self._soup.find(id="page_genre_description_full").text
        
    def _fetch_akas(self):
        if aka_elems := self._soup.find_all("bdi", class_="comma_separated"):
            return [aka.text for aka in aka_elems]
        
    def _fetch_parent_genres(self):
        parent_elems = self._soup.find_all("li", class_="hierarchy_list_item parent")
        return [SimpleGenre(name= parent.contents[1].contents[1].text, url= ROOT_URL + parent.contents[1].contents[1]["href"]) for parent in parent_elems] or None
    
    def _fetch_children_genres(self):
        genre_elem = self._soup.find("li", class_="hierarchy_list_item hierarchy_list_item_current")
        children_elems = genre_elem.find_next_sibling().contents
        children_genres = list()
        for i in range(1, len(children_elems), 2):
            url = ROOT_URL + children_elems[i].contents[1].contents[1].contents[1]["href"]
            name = children_elems[i].contents[1].contents[1].contents[1].text
            children_genres.append(SimpleGenre(name=name, url=url))
        return children_genres or None
    
    def _fetch_top_ten(self):
        return

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Genre: {self.name}"
        
class Artist:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url) -> None:
        self._cached_rym_response = requests.get(url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.url = url
        self.name = self._fetch_name()
        self.localized_name = self._fetch_localized()
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
        self.related_artists = self._fetch_related()
        self.notes = self._fetch_notes()
        self.discography = self.ReleaseCollection(self._soup)
        self.appears_on = self.FeatureCollection(self._soup)
        self._credits = None

    class GeneralCollection:
        def __init__(self, artist_soup: bs4.BeautifulSoup) -> None:
            self._soup = artist_soup
            self.albums = None
            self.live_albums = None
            self.eps = None
            self.compilations = None
            self.singles = None
            self.video_releases = None
            self.unauthorized_releases = None
            self.mixtapes = None
            self.music_videos = None
            self.dj_mixes = None
            self.additional_releases = None
            self.other = None
            self.initialize_attributes()

        @property
        def bootlegs(self):
            return self.unauthorized_releases
        
        def create_simple_release(self, release):
            def get_release_date(elem):
                if not elem.get("title"):
                    return None
                
                date_components_count = elem["title"].count(" ") + 1
                date_formating = {1: "%Y",
                                2: "%B %Y",
                                3: "%d %B %Y"}
                
                return datetime.strptime(elem["title"], date_formating[date_components_count])
            
            return SimpleRelease(name=release.find(class_="disco_info").contents[0]["title"],
                                  url= ROOT_URL + release.find(class_="disco_info").contents[0]["href"],
                                  release_date=get_release_date(release.find(class_="disco_subline")),
                                  number_of_ratings=release.find(class_="disco_ratings").text or None,
                                  number_of_rewviews=release.find(class_="disco_reviews").text or None,
                                  average_rating=float(release.find(class_="disco_avg_rating").text))

    class ReleaseCollection(GeneralCollection):
        def initialize_attributes(self):
            self.albums = self._fetch_releases("s")
            self.live_albums = self._fetch_releases("l")
            self.eps = self._fetch_releases("e")
            self.compilations = self._fetch_releases("c")
            self.singles = self._fetch_releases("i")
            self.video_releases = self._fetch_releases("d")
            self.unauthorized_releases = self._fetch_releases("b")
            self.mixtapes = self._fetch_releases("m")
            self.music_videos = self._fetch_releases("o")
            self.dj_mixes = self._fetch_releases("j")
            self.additional_releases = self._fetch_releases("x")

        def _fetch_releases(self, type_of_release):
            releases_elem = self._soup.find(id="disco_type_" + type_of_release)

            if not releases_elem:
                return None

            return [self.create_simple_release(release) for release in releases_elem.find_all(class_="disco_release")]
        
    class FeatureCollection(GeneralCollection):
        def initialize_attributes(self):
            
            releases_elem = self._soup.find(id="disco_type_a")

            if not releases_elem:
                return None

            for release in releases_elem.find_all(class_="disco_release"):
                release_object = self.create_simple_release(release)
               
                release_type_init = release.find(class_="disco_subline").find(class_="subtext").text
                release_type = release_type_init.split('•')[1].strip()
                
                match release_type:
                    case "Album":
                        if self.albums is None:
                            self.albums = list()
                        self.albums.append(release_object)
                    
                    case "EP":
                        if self.eps is None:
                            self.eps = list()
                        self.eps.append(release_object)
                    
                    case "Single":
                        if self.singles is None:
                            self.singles = list()
                        self.singles.append(release_object)
                    
                    case "Mixtape":
                        if self.mixtapes is None:
                            self.mixtapes = list()
                        self.mixtapes.append(release_object)
                    
                    case "Music video":
                        if self.music_videos is None:
                            self.music_videos = list()
                        self.music_video.append(release_object)
                    
                    case "DJ Mix":
                        if self.dj_mixes is None:
                            self.dj_mixes = list()
                        self.dj_mixes.append(release_object)
                    
                    case "Video":
                        if self.video_releases is None:
                            self.video_releases = list()
                        self.video_releases.append(release_object)
                    
                    case "Compilation":
                        if self.compilations is None:
                            self.compilations = list()
                        self.compilations.append(release_object)
                    
                    case "Additional release":
                        if self.additional_releases is None:
                            self.additional_releases = list()
                        self.additional_releases.append(release_object)
                    
                    case "Bootleg/Unauthorized":
                        if self.unauthorized_releases is None:
                            self.unauthorized_releases = list()
                        self.unauthorized_releases.append(release_object)
                    
                    case _:
                        if self.other is None:
                            self.other = list()
                        self.other.append(release_object)

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
    
    @property
    def credits(self):
        if not self._credits:
            self._credits = self._fetch_credits()
        return self._credits

    def _fetch_name(self):
        try:
            return self._soup.find("h1", class_="artist_name_hdr").text
        except AttributeError:
            raise ParseError("No artist name was found.")
        
    def _fetch_localized(self):
        localized_elem = self._soup.find("span", {"style":"margin-left:5px;font-size:0.7em;color:var(--mono-6);"})
        if localized_elem:
            return localized_elem.text
        
    def _fetch_location(self, date_location_elem):
        if location_elem := date_location_elem.find("a", class_="location"):
            location_list = location_elem.text.split(", ")
            if len(location_list) == 3:
                return Location(city=location_list[0], state=location_list[1], country=location_list[2], url=location_elem["href"])
            elif len(location_list) == 2:
                return Location(state=location_list[0], country=location_list[1], url=location_elem["href"])
            else:
                return Location(country=location_list[0], url=location_elem["href"])

    def _fetch_gen_date_location(self, *titles):
        for title in titles:
            if (date_location_elem := self._soup.find("div", class_="info_hdr", string=title)):
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
        if genre_div := self._soup.find("div", class_="info_hdr", string="Genres"):
            genres_elem = genre_div.find_next_sibling()
            return [SimpleGenre(name=genre.lstrip()) for genre in genres_elem.text.split(",")]

    def _fetch_members(self):
        if members_div := self._soup.find("div", class_="info_hdr", string="Members"):
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
        if aka_div := self._soup.find("div", class_="info_hdr", string="Also Known As"):
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
        
    def _fetch_related(self):
        if related_div := self._soup.find("div", class_="info_hdr", string="Related Artists"):
            related_elem = related_div.find_next_sibling()
            artist_elems = related_elem.find_all("a")
            return [SimpleArtist(name=artist.text, url=artist["href"]) for artist in artist_elems]
        
    def _fetch_notes(self):
        if notes_div := self._soup.find("div", class_="info_hdr", string="Notes"):
            notes_elem = notes_div.find_next_sibling()
            return notes_elem.text

    def _fetch_credits(self):
        credits_url = (self.url + "/credits/").replace("//", "/")
        credits_response = requests.get(credits_url, headers= HEADERS)
        if credits_response.status_code != 200:
            raise RequestFailed(f"Credits request failed with status code {self._cached_rym_response.status_code}")
        credits_soup = bs4.BeautifulSoup(credits_response.content, "html.parser")
        credited_releases = credits_soup.find_all(class_="disco_release")

        def get_roles(elem):
            return [Role(name=role) for role in elem.text.split(",")]

        return [CreditedRelease(name=release.find(class_="album").text,
                                url=release.find(class_="album")["href"],
                                roles=get_roles(release.find(class_="disco_classical_role"))
                                ) for release in credited_releases]


    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Artist: {self.name}"

class Track:
    def __init__(self, *, number, title, length, credited_artists=None, release) -> None:
        self.number = number
        self.title = title
        self.length = length
        self.credited_artists = credited_artists
        self.release = release

    def __eq__(self, other) -> bool:
        return self.number == other.number and self.release == other.release

class Release:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url) -> None:
        self._cached_rym_response = requests.get(url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.url = url
        self.title = self._fetch_title()
        self.artists = self._fetch_artists()
        self.artist_name = self._fetch_artist_name()
        self.average_rating = self._fetch_average_rating()
        self.number_of_ratings = self._fetch_number_of_ratings()
        self.number_of_reviews = self._fetch_number_of_reviews()
        self.release_date = self._fetch_release_date()
        self.recording_date = self._fetch_recording_date()
        self.type = self._fetch_type()
        self.primary_genres = self._fetch_primary_genres()
        self.secondary_genres = self._fetch_secondary_genres()
        self.descriptors = self._fetch_descriptors()
        self.cover_url = self._fetch_cover_url()
        self.links = self._fetch_release_links()
        self.tracklist = self._fetch_tracks()
        self.length = self._fetch_length()
        self.credited_artists = self._fetch_credited_artists()
        self.__update_tracks()
        self.reviews = self._fetch_reviews()
        self.lists = None
        self._id = self._fetch_id()

    class EntryCollection:
        @sleep_and_retry
        @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
        def __init__(self, url) -> None:
            self.init_url = url
            self.current_url = url
            self._cached_rym_response = requests.get(self.init_url, headers= HEADERS)
            if self._cached_rym_response.status_code != 200:
                raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}.")
            self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
            self.current_page = 1
            self.max_page = self._fetch_max_page()
            if self.current_page > self.max_page:
                raise NoContent("This release has no lists.")
            self.entries = self._fetch_entries(init=True)

        def _fetch_max_page(self):
            try:
                return int(self._soup.find_all("a", class_="navlinknum")[-1].text)
            except IndexError:
                return 0
            
        def load_more_entries(self):
            self.current_page += 1
            self.current_url = re.sub(r"\d+\/$", f"{self.current_page}/", self.current_url)
            self.entries += self._fetch_entries()
            return self
        
        def _fetch_entries(self, init=False):
            if self.current_page > self.max_page:
                raise NoContent("No more pages to be loaded.")
            
            if not init:
                self._cached_rym_response = requests.get(self.current_url, headers= HEADERS)
                if self._cached_rym_response.status_code != 200:
                    raise RequestFailed(f"Loading next page failed with status code {self._cached_rym_response.status_code}.")
                self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")

            self._specific_fetch()

    class Lists(EntryCollection):
        def _specific_fetch(self):
            lists_elem = self._soup.find("ul", class_="lists expanded").contents
            return [SimpleList(
                title= entry.contents[3].contents[1].contents[0].text,
                url= ROOT_URL + entry.contents[3].contents[1].contents[0]["href"]
                ) for entry in lists_elem[1::2]]
        
    class Reviews(EntryCollection):
        def _specific_fetch(self):
            curr_elem = self._soup.find(class_="review_list")
            reviews = list()

            while True:
                try:
                    curr_elem = curr_elem.next_sibling.next_sibling

                    review_content = str()
                    if review_elem := curr_elem.find(class_="page_review_feature_body_inner"):
                        review_content = review_elem.text
                    
                    rating = None
                    if rating_elem := curr_elem.find(class_="page_review_feature_rating"):
                        rating = float(rating_elem["content"])
                    
                    review_date_text = curr_elem.find(class_="review_date").contents[1].text
                    review_date = datetime.strptime(review_date_text, "%B %d %Y")

                    reviews.append(Review(
                        url=ROOT_URL + curr_elem.find(class_="review_date").contents[1]["href"],
                        content=review_content,
                        rating=rating,
                        release=self,
                        date=review_date,
                        request_needed=False
                    ))
                except AttributeError:
                    return reviews
    
    @property
    def lists(self):
        if not self._lists:
            self._lists = self.Lists((self.url + "/lists/1/").replace("//","/"))
        return self._lists

    @property
    def reviews(self):
        if not self._reviews:
            self._reviews = self.Reviews((self.url + "/lists/1/").replace("//","/"))
        return self._reviews

    def get_track_by_title(self, title):
        for track in self.tracklist:
            if track.title == title:
                return track
            
    def get_track_by_number(self, number):
        for track in self.tracklist:
            if track.number == number:
                return track

    def _fetch_title(self):
        release_title_elem = self._soup.find("div", class_="album_title")
        try:
            return re.findall(r"(.+)\n +\nBy .+", release_title_elem.text)[0]
        except IndexError:
            raise ParseError("No title was found for this release.")
        
    def _fetch_artists(self):
        outer_elem = self._soup.find("span", {"itemprop":"byArtist"})
        artists_elem = outer_elem.find_all("a", class_="artist")
        return [SimpleArtist(name=artist.text, url=ROOT_URL+artist["href"]) for artist in artists_elem]
    
    def _fetch_artist_name(self):
        outer_elem = self._soup.find("span", {"itemprop":"byArtist"})
        if collab_name := outer_elem.find(class_="credited_name"):
            return collab_name.text
        else:
            return outer_elem.text
    
    def _fetch_average_rating(self):
        if average_rating_elem := self._soup.find("span", class_="avg_rating"):
            return average_rating_elem.text.strip()
        
    def _fetch_number_of_ratings(self):
        if num_ratings_elem := self._soup.find("span", class_="num_ratings"):
            return num_ratings_elem.contents[1].text.strip()
        
    def _fetch_number_of_reviews(self):
        if review_section := self._soup.find("div", class_="section_reviews section_outer"):
            reviews_elem_split = review_section.find("div", class_="release_page_header").text.split(" ")
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
        if genres_elem := self._soup.find("span", class_=f"release_{type}_genres"):
            genres_text = genres_elem.text
            return [SimpleGenre(name=genre.lstrip()) for genre in genres_text.split(",")]
    
    def _fetch_primary_genres(self):
        return self._gen_fetch_genres("pri")

    def _fetch_secondary_genres(self):
        return self._gen_fetch_genres("sec")
    
    def _fetch_descriptors(self):
        if descriptors := self._soup.find("span", class_="release_pri_descriptors"):
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
        if release_links_elem := self._soup.find("div", id="media_link_button_container_top"):
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
            track_number = track.contents[0].find("span", class_="tracklist_num").text.replace("\n","").replace(" ", "")
            track_title = track.contents[0].find("span", class_="tracklist_title").text
            track_length = timedelta(seconds=int(tracks.find("span", class_="tracklist_title").contents[1]["data-inseconds"]))
            tracks.append(Track(number=track_number, title=track_title, length=track_length))
        
        return tracks
    
    def _fetch_credited_artists(self):
        def get_role_tracks(text):
            result_tuples = re.findall(r"(\w+-\w+)|(\w+)", text)
            role_tracks = list()

            for (result1, result2) in result_tuples:
                if result1:
                    start_stop_tracks = result1.split("-")
                    start_flag = False
                    for track in self.tracklist:
                        if track.number == start_stop_tracks[1]:
                            break
                        if track.number == start_stop_tracks[0]:
                            start_flag = True
                        if start_flag:
                            role_tracks.append(track)
                elif result2:
                    role_tracks.append(self.get_track_by_number(result2))

            return role_tracks

        credits_elem = self._soup.find(id="credits_")
        credited_artists = list()

        for artist in credits_elem[::2]:
            role_elems = credits_elem.contents[0].find_all(class_="role_name")
            roles = [Role(name=role.contents[0].text, tracks= get_role_tracks(role.contents[1].text)) for role in role_elems]
            
            url = str()
            if artist.contents[0].get("href"):
                url = ROOT_URL+artist.contents[0].get("href")

            credited_artists.append(CreditedArtist(name=artist.contents[0].text, 
                                                       url=url,
                                                       roles=roles))


        return credited_artists
    
    def __update_tracks(self):
        new_credited_artist = list()

        for credited_artist in self.credited_artists:
            new_roles = list()

            for role in credited_artist.roles:
                new_tracks = list()

                for track in role.tracks:
                    if track in self.tracklist:
                        track.credited_artists = credited_artist
                        new_tracks.append(track)
                        self.tracklist[self.tracklist.index(track)] = track
                
                role.tracks = new_tracks
                new_roles.append(role)

            credited_artist.roles = new_roles
            new_credited_artist.append(credited_artist)
        
        self.credited_artists = new_credited_artist
    
    def _fetch_length(self):
        release_length_elem = self._soup.find("span", class_="tracklist_total")
        
        if not release_length_elem:
            return None
        
        length_raw = re.findall(r"(\d+):(\d+)", release_length_elem.text)
        
        if not length_raw:
            return None
        
        minutes = 0
        seconds = 0
        
        if length_raw[0][0]:
            minutes = int(length_raw[0][0])
        
        if length_raw[0][1]:
            seconds = int(length_raw[0][1])

        return timedelta(minutes=minutes, seconds=seconds)
                
    def _fetch_id(self):
        id_elem = self._soup.find("input", class_="album_shortcut")
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
        self.username = username or re.search(r"[\w+|_]+$", url).group()
        if not username:
            raise NoURL("No valid username or URL provided.")
        self.url = url or f"{ROOT_URL}/~{username}"
        self._cached_rym_response = requests.get(self.url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.favorite_artists = self._fetch_favorite_artists()
        self.recently_online_friends = self._fetch_recently_online_friends()
        self._friends = None

    @property
    def favourite_artists(self):
        return self.favorite_artists
    
    @property
    def friends(self):
        if not self._friends:
            self._friends = self._fetch_friends()
        return self._friends
    
    def _fetch_favorite_artists(self):
        title_elem = self._soup.find(class_="bubble_header", string="favorite artists")
        if not title_elem:
            return None
        fav_artists_elem = title_elem.next_sibling.contents[1].contents[1]
        return [SimpleArtist(name=artist_elem.text.lstrip(),
                             url=artist_elem["href"])
                             for artist_elem in fav_artists_elem
                             if artist_elem.name == "a" and artist_elem.get("title") and artist_elem["title"].startswith("[Artist")]
    
    def _fetch_recently_online_friends(self):
        friends_elem = self._soup.find(id="ftabfriends")
        if not friends_elem:
            return None
        return [SimpleUser(name= friend.text) for friend in friends_elem.find_all("td")]
    
    def _fetch_friends(self):
        friends_url = self.url.replace("~", "friends/")
        friends_request = requests.get(friends_url, headers= HEADERS)
        friends_soup = bs4.BeautifulSoup(friends_request.content, "html.parser")
        friends_elem = friends_soup.find_all(class_="or_card_frame_inner")
        if friends_elem:
            return [SimpleUser(name= friend.text.replace("\n   \n","")) for friend in friends_elem]
        
class RYMList:
    def __init__(self, url) -> None:
        self.init_url = url
        self.current_url = self.init_url
        self._cached_rym_response = requests.get(self.init_url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.author = self._fetch_author()
        self.content = self._fetch_entries()
        self.current_page = 1
        if not self._soup.find("a", class_="navlinknext"):
            raise NoContent("The requested chart has no entries.")
        self.content = self._fetch_entries(init=True)
        self._id = self._fetch_id()
        
    def _fetch_entries(self, init=False):
        # no clue how to get around with this yet
        '''if not init:
            self._cached_rym_response = requests.get(self.current_url, headers= HEADERS)
            if self._cached_rym_response.status_code != 200:
                raise RequestFailed(f"Loading next page failed with status code {self._cached_rym_response.status_code}.")
            self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        
        if not self._soup.find("a", class_="navlinknext"):
            raise NoContent("No more pages to be loaded.")

        list_elem = self._soup.find("table", {"id":"user_list").contents
        entries = [SimpleList() for entry in list_elem[:-1:2]]
        
        return entries'''

    def load_more_entries(self):
        self.current_page += 1
        self.current_url = re.sub(r"\d+\/$", f"{self.current_page}/", self.current_url)
        self.content += self._fetch_entries()
        return self
    
class Review:
    def __init__(self, *, url, author=None, content=None, rating=None, release:Release=None, date=None, request_needed=True) -> None:
        self.url = url
        self.content = content
        self.rating = rating
        self.author = author
        self.date = date
        self.release = release
        if request_needed:
            self._cached_rym_response = requests.get(url, headers= HEADERS)
            if self._cached_rym_response.status_code != 200:
                raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}")
            self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
            self.content = content or self._fetch_content()
            self.rating = rating or self._fetch_rating()
            self.author = author or self._fetch_author()
            self.simplified_releade = SimpleRelease(title= self._fetch_release_title(), url= self._fetch_release_url())

    def _fetch_content(self):
        if review_elem := self._soup.find(class_="page_review_feature_body_inner"):
            return review_elem.text
        
    def _fetch_author(self):
        try:
            return SimpleUser(name=self._soup.find(class_="user").text)
        except AttributeError:
            raise NoContent("No author was found for the review.")

    def _fetch_release_title(self):
        try:
            return self._soup.find(class_="album").text
        except AttributeError:
            raise NoContent("No title was found for the release.")
    
    def _fetch_release_url(self):
        try:
            return ROOT_URL + self._soup.find(class_="album")["href"]
        except KeyError:
            raise NoContent("No URL was found for the release.")
        
    def _fetch_rating(self):
        rating_elem = self._soup.find(class_="page_review_feature_rating")
        if not rating_elem:
            return None
        return float(rating_elem["content"])

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
    def __init__(self, *, name=None, title=None, url=None) -> None:
        self.title = name or title
        self.url = url

    @property
    def name(self):
        return self.title

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
    def __init__(self, *, name=None, release_date=None, average_rating=None, number_of_ratings=None, number_of_reviews=None, url=None):
        super().__init__(name=name, url=url)
        self.release_date = release_date
        self.average_rating = average_rating
        self.number_of_ratings = number_of_ratings
        self.number_of_reviews = number_of_reviews

    def get_release(self):
        return Release(self.url)
    
class SimpleList(SimpleEntity):
    def get_list(self):
        return RYMList(self.url)
    
class SimpleUser(SimpleEntity):
    def get_user(self):
        return User(username=self.name, url=self.url)
    
class BandMember(SimpleArtist):
    def __init__(self, *, name, instruments, years_active, aka, url=None):
        super().__init__(name=name, url=url)
        self.instruments = instruments
        self.years_active = years_active
        self.aka = aka

class CreditedArtist(SimpleArtist):
    def __init__(self, *, name, url=None, roles):
        super().__init__(name=name, url=url)
        self.roles = roles

class CreditedRelease(CreditedArtist):
    def get_release(self):
        return Release(self.url)

class Role:
    def __init__(self, *, name, tracks=None, credited_artist= None) -> None:
        self.name = name
        self.tracks = tracks
        self.credited_artist = credited_artist

    def __repr__(self):
        return self.__get_representation()

    def __str__(self):
        return self.__get_representation()
    
    def __get_representation(self):
        if self.tracks:
            return f"{self.name} in {','.join([track.name for track in self.tracks])}"
        else:
            return self.name

class ChartType:
    top = "top"
    bottom = "bottom"
    esoteric = "esoteric"
    diverse = "diverse"
    popular = "popular"

class YearRange:
    def __init__(self, *, min, max) -> None:
        self.min = min
        self.max = max

class ReleaseType:
    album = "album"
    ep = "ep"
    comp = "comp"
    single = "single"
    video = "video"
    unauthorized = "unauth"
    bootleg = "unauth"
    mixtape = "mixtape"
    music_video = "musicvideo"
    dj_mix = "djmix"
    additional = "additional"

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