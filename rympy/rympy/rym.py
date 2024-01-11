import requests
import re
from datetime import datetime
from datetime import timedelta
from typing import List
import json
import bs4
from ratelimit import limits, sleep_and_retry
from .enums import *
from .exceptions import *
from .global_variables import *
from .base_classes import *

class Chart(EntryCollection):
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, *, type, release_types,
                 year_range=None, primary_genres=None,
                 secondary_genres=None, primary_genres_excluded=None,
                 secondary_genres_excluded=None, locations=None,
                 locations_excluded=None, languages=None,
                 languages_excluded=None, descriptors=None,
                 descriptors_excluded=None, include_subgenres=True,
                 contain_all_genres=False) -> None:
        self.init_url = self._fetch_url()
        super().__init__(self.init_url, "ui_pagination_btn ui_pagination_number")
        self.type = type
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

    def _specific_fetch(self):
        chart_elem = self._soup.find("section", id="page_charts_section_charts").contents
        entries = [SimpleRelease(title=(entry.find("div", class_="page_charts_section_charts_item_credited_links_primary")
                                        .text.replace("\n", "") + " - " + entry.find("div", class_="page_charts_section_charts_item_title")
                                        .text.replace("\n", "")),
                                 url=ROOT_URL + entry.contents[1].contents[1]["href"]
                                 ) for entry in chart_elem[:-1:2]]
        
        return entries
    
    def __str__(self):
        return self._get_representation()

    def __repr__(self):
        return self._get_representation()

    def _get_representation(self):
        return f"Chart: {self.type} {' '.join(self.release_types)}"

class Genre:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, *, url=None, name=None) -> None:
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
        self.lists = self._fetch_lists()
        self._oldest_releases = None
        self._newest_releases = None

    class GenreReleases(EntryCollection):
        def __init__(self, url):
            super().__init__(url, "ui_pagination_btn ui_pagination_number")
        
        def _specific_fetch(self):
            def get_cover(found_a):
                if picture_elem := found_a.find("picture"):
                    return picture_elem.find("source")["srcset"].replace("\n","").strip().split(" 2x")[0]
            
            release_elems = self._soup.find_all(class_="component_discography_item")
            return [SimpleRelease(url=ROOT_URL+release.find("a")["href"],
                                  cover=get_cover(release.find("a")),
                                  title=release.find("span").text.replace("\n",""),
                                  artist_name=release.find("span").next_sibling.next_sibling.text.replace("\n",""),
                                  simple_artists=[SimpleArtist(name=artist.text.replace("\n",""),
                                                               url=ROOT_URL+artist["href"]
                                                               ) for artist in release.find("span").next_sibling.next_sibling.find_all(class_="artist")["href"]]
                                  ) for release in release_elems]

    @property
    def oldest_releases(self):
        if not self._oldest_releases:
            self._oldest_releases = self.GenreReleases(ROOT_URL + "/genres/" + self.name.lower().replace(" ", "-") + "/1/")
        return self._oldest_releases
    
    @property
    def newest_releases(self):
        if not self._newest_releases:
            self._newest_releases = self.GenreReleases(ROOT_URL + "/genres/" + self.name.lower().replace(" ", "-") + "/1.d/")
        return self._newest_releases
    
    @property
    def releases(self):
        return self.oldest_releases

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
        return self._soup.find(id="page_genre_description_short").text.replace("\n","").replace("Read more","")
        
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
        def get_cover(found_a):
            if picture_elem := found_a.find("picture"):
                return picture_elem.find("source").get("srcset") or picture_elem.find("source").get("data-srcset").replace("\n","").strip().split(" 2x")[0]
            
        top_ten_elem = self._soup.find_all(class_="page_section_charts_carousel_item")
        return [SimpleRelease(name=album.find(class_="release").text,
                              artist_name=album.find(class_="artist").text,
                              url=album.find("a")["href"],
                              cover=(get_cover(album.find("a")))
                              ) for album in top_ten_elem]
    
    def _fetch_lists(self):
        rym_lists = self._soup.find_all(class_="page_section_lists_list")
        return [SimpleRYMList(title=rym_list.find(class_="main").text.replace("\n","").strip(),
                              url=ROOT_URL+rym_list.find(class_="main").find("a")["href"],
                              author=SimpleUser(name=rym_list.find_all(class_="page_section_lists_list_main_line")[1].find("a").text,
                                                url=ROOT_URL+rym_list.find_all(class_="page_section_lists_list_main_line")[1].find("a")["href"])
                              ) for rym_list in rym_lists]

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Genre: {self.name}"
        
class Artist:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, *, url=None, name=None, same_name_artist_number=0) -> None:
        if not url:
            if not name:
                raise NoURL("No valid artist name or URL provided.")
            else:
                url = ROOT_URL + "/artist/" + name.replace(" ", "-").lower()
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
        self.member_of = self._fetch_member_of()
        self.related_artists = self._fetch_related()
        self.notes = self._fetch_notes()
        self._credits = None
        self.discography = self.ReleaseCollection(self)
        self.appears_on = self.FeatureCollection(self)
        self.same_name_artist_number = same_name_artist_number

    class GeneralCollection:
        def __init__(self, artist) -> None:
            self.artist = artist
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
            date = None
            if date_elem := release.find(class_="disco_subline"):
                date_text = date_elem.find("span")["title"]
                date_components_count = date_text.count(" ") + 1
                date_formating = {1: "%Y",
                                2: "%B %Y",
                                3: "%d %B %Y"}
                
                date = datetime.strptime(date_text, date_formating[date_components_count])

            artist_name = self.artist.name
            artists = [self.artist]
            if collab_elem := self.artist._soup.find(class_="credited_name"):
                artist_name = collab_elem.contents[0].text
                artists = [SimpleArtist(name=artist.text, url=ROOT_URL + artist["href"])
                           if ROOT_URL + artist["href"] != self.artist.url else self.artist
                           for artist in collab_elem.find_all(class_="disco_sub_artist")]
            elif artist_elem := release.find(class_="disco_sub_artist"):
                artist_name = artist_elem.text
                artist_url = ROOT_URL + artist_elem["href"]
                if artist_url != self.artist.url:
                    artists = [SimpleArtist(name=artist_name, url=artist_url)]
            
            return SimpleRelease(name=release.find(class_="disco_info").contents[0]["title"],
                                 artist_name=artist_name,
                                 artists=artists,
                                 url= ROOT_URL + release.find(class_="disco_info").contents[0]["href"],
                                 release_date=date,
                                 number_of_ratings=release.find(class_="disco_ratings").text or None,
                                 number_of_reviews=release.find(class_="disco_reviews").text or None,
                                 average_rating=(lambda x: float(x.text) if x else None)(release.find(class_="disco_avg_rating")))

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
            self.various_artists_compilations = self._fetch_releases("v")

        def _fetch_releases(self, type_of_release):
            releases_elem = self.artist._soup.find(id="disco_type_" + type_of_release)

            if not releases_elem:
                return None

            return [self.create_simple_release(release) for release in releases_elem.find_all(class_="disco_release")]
        
    class FeatureCollection(GeneralCollection):
        def initialize_attributes(self):
            
            releases_elem = self.artist._soup.find(id="disco_type_a")

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
                        self.music_videos.append(release_object)
                    
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
    
    def next_same_name_artist(self):
        return Artist(name=self.name, same_name_artist_number=self.same_name_artist_number+1)

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
                location = self._fetch_location(date_location_elem)
                date_location_info = date_location_elem.find_next_sibling()
                if date_location_info.contents[0].name != "a":
                    date_text = date_location_info.contents[0].strip()[:-1]
                    date_components_count = date_text.count(" ") + 1
                    date_formating = {1: "%Y",
                                    2: "%B %Y",
                                    3: "%d %B %Y"}
                    try:
                        date = datetime.strptime(date_text, date_formating[date_components_count])
                    except ValueError:
                        date = None
                else:
                    date = None

                return {"date": date,
                        "location": location}
        
        return {"date": None,
                "location": None}

    def _fetch_start_date_location(self):
        return self._fetch_gen_date_location("Formed", ["Formed","Born"])

    def _fetch_end_date_location(self):
        return self._fetch_gen_date_location("Disbanded", ["Disbanded","Died"])
    
    def _fetch_current_location(self):
        if (date_location_elem := self._soup.find("div", class_="info_hdr", string="Currently")):
            return date_location_elem.find_next_sibling().text


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
        
    def _fetch_member_of(self):
        if member_of_div := self._soup.find("div", class_="info_hdr", string="Member of"):
            member_of = member_of_div.find_next_sibling()
            all_artists = member_of.split(", ")
            artist_elems = member_of.find_all("a")
            return [SimpleArtist(name=artist.text, url=artist["href"])
                    for artist in artist_elems] + [artist for artist in all_artists if artist not in
                                                   [artist.text for artist in artist_elems]]
        
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
    def __init__(self, *, number, title, length, credited_artists=None, release=None, simple_release=None) -> None:
        self.number = number
        self.title = title
        self.length = length
        self.credited_artists = credited_artists
        self.release = release
        self.simple_release = simple_release

    def __eq__(self, other) -> bool:
        return self.number == other.number and self.release == other.release

class Distributor:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url) -> None:
        self.url = url
        self._cached_rym_response = requests.get(url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}.")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.name = self._fetch_name()
        self.logo = self._fetch_logo()
        self.profile = self._fetch_profile()

    def _fetch_name(self):
        return self._soup.find(id="wiki_content").find(class_="bubble_header").contents[0].text
    
    def _fetch_logo(self):
        return self._soup.find(class_="wiki-image")["src"]
    
    def _fetch_profile(self):
        init_elem = self._soup.find("h2")
        curr_elem = init_elem
        profile_text = str()
        while True:
            try:
                curr_elem = init_elem.find_next_sibling()
            except AttributeError:
                return profile_text
            else:
                profile_text = curr_elem.text if curr_elem.name != "br" else "\n"

class Label:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url) -> None:
        self.url = url
        self._cached_rym_response = requests.get(url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}.")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.name = self._fetch_name()
        self.logo = self._fetch_logo()
        self.genres = self._fetch_genres()
        self.number_of_releases = self._fetch_no_releases()
        self.founder = self._fetch_founder()
        self.start_date = self._fetch_start_date()
        self.start_location = self._fetch_start_location()
        self.links = self._fetch_links()
        self.address = self._fetch_address()
        self.distributors = self._fetch_distributors()
        self.notes = self._fetch_notes()
        self._chart = None
    
    @property
    def chart(self):
        if not self._chart:
            self._chart = self._fetch_chart()
        return self._chart

    def _fetch_name(self):
        try:
            return self._soup.find(class_="page_company_music_section_name_inner").find("h1").text
        except AttributeError:
            raise ParseError("No label name was found.")
        
    def _fetch_logo(self):
        return self._soup.find("picture").find_all("img")[-1]["src"]
    
    def _fetch_genres(self):
        genre_list = [genre.strip() for genre in self._soup.find(class_="page_company_music_genres").split(", ")]
        return [SimpleGenre(name=genre) for genre in genre_list]
    
    def _fetch_no_releases(self):
        number_elem_text = self._soup.find(class_="page_company_music_release_count").text.replace(",", "")
        return int(re.search(r'\d+', number_elem_text).group())
    
    def _fetch_founder(self):
        if artist_elem := self._soup.find(class_="page_company_music_main_info_founded_main").find(class_="artist"):
            return SimpleArtist(name=artist_elem.text,
                                url=ROOT_URL+artist_elem["href"])
        
    def _fetch_start_date(self):
        date_text = self._soup.find(class_="page_company_music_main_info_founded_main").find("b").text
        return datetime.strptime(date_text, "%Y")
    
    def _fetch_start_location(self):
        location_text = self._soup.find(class_="page_company_music_main_info_founded_location").text.replace("\n","").strip()
        return location_text.split(", ")
    
    def _fetch_links(self):
        return {link["aria-label"].lower():link["href"] for link in self._soup.find(class_="links").find_all("a")}
    
    def _fetch_address(self):
        address_text_list = ["\n" if elem.name == "br" else elem.text for elem in self._soup.find(class_="address").contents]
        return "".join(address_text_list)
    
    def _fetch_distributors(self):
        if not(distributors_title := self._soup.find("td", string="Distributors")):
            return None
        
        distributors_elem = distributors_title.find_next_sibling()
        distributors_elems_list = distributors_elem.contents[0].contents
        distributors_elems_urls = [distributor for distributor in distributors_elems_list if isinstance(distributor, bs4.Tag) and distributor.get("href")]
        distributors_elem_raw = distributors_elem.text
        distributors_name_info = re.findall(r" ?([\w .]+) (?:\[([\w -]+)\])", distributors_elem_raw)
        distributors = list()

        urls_index = 0
        for name, years in distributors_name_info:
            url = None
            if urls_index < len(distributors_elems_urls) and distributors_elems_urls[urls_index].text == name:
                url = ROOT_URL + distributors_elems_urls[urls_index]["href"]
                urls_index += 1

            if "/label/" in url:
                distributors.append(LabelDistributor(name=name, years=years, url=url))
            else:
                distributors.append(SimpleDistributor(name=name, years=years, url=url))
            
        return distributors

    def _fetch_notes(self):
        if notes_elem := self._soup.find("td", string="Notes"):
            return notes_elem.find_next_sibling().text
        
    def _fetch_chart(self):
        outer_elem = self._soup.find(class_="page_section_charts link_only")
        if outer_elem:
            return Chart(ROOT_URL + outer_elem.find("a")["href"])
        
        outer_elem = self._soup.find(class_="page_section_charts_header")
        if outer_elem:
            return Chart(ROOT_URL + outer_elem.find("a")["href"])

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
        self.issues = self._fetch_issues()
        self.__update_tracks()
        self._reviews = None
        self._lists = None
        self.id = self._fetch_id()
        self.is_nazi = self._fetch_is_nazi()

    class Lists(EntryCollection):
        def __init__(self, url):
            super().__init__(url, "navlinknum")
            
        def _specific_fetch(self):
            lists_elem = self._soup.find("ul", class_="lists expanded").contents
            return [SimpleRYMList(
                title= entry.contents[3].contents[1].contents[0].text,
                url= ROOT_URL + entry.contents[3].contents[1].contents[0]["href"]
                ) for entry in lists_elem[1::2]]
        
    class Reviews(EntryCollection):
        def __init__(self, url):
            super().__init__(url, "navlinknum")

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
            return re.findall(r"(.+)\n +\nBy .+", release_title_elem.text)[0].strip()
        except IndexError:
            raise ParseError("No title was found for this release.")

    def _fetch_artists(self):
        if "/comp/various-artists/" in self.url:
            self.various_artists = True
            return [SimpleArtist(name=artist.text,url=ROOT_URL+artist["href"]) for artist in self._soup.find(id="tracks").find_all("a")]
        
        self.various_artists = False
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
            return types_proto[0]

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
            return descriptors.text.split(", ")

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

        for track in tracks_elem.find_all("div", {"itemprop":"track"}):
            track_number = track.find("span", class_="tracklist_num").text.replace("\n","").replace(" ", "")
            track_title = track.find("span", class_="tracklist_title").text
            track_length = timedelta(seconds=int(track.find("span", class_="tracklist_title").contents[1]["data-inseconds"]))
            tracks.append(Track(number=track_number, title=track_title, length=track_length, simple_release=SimpleRelease(title=self.title,
                                                                                                                          url=self.url)))
        
        return tracks
    
    def _fetch_credited_artists(self):
        def get_role_tracks(role_tracks_elem):
            if not role_tracks_elem:
                return None
            text = role_tracks_elem.text
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

        if not credits_elem:
            return credited_artists

        for artist in credits_elem.find_all("li"):
            if not artist.text or "expand_button" in artist.get("class"):
                continue
            role_elems = credits_elem.contents[0].find_all(class_="role_name")
            roles = [Role(name=role.contents[0].text, tracks= get_role_tracks(role.find(class_="role_tracks"))) for role in role_elems]
            
            url = str()
            artist_name = str()
            try:
                if artist.contents[0].get("href"):
                    url = ROOT_URL+artist.contents[0].get("href")
                artist_name = artist.contents[0].text
            except (IndexError, AttributeError):
                artist_name = str(artist.contents[0])

            credited_artists.append(CreditedArtist(name=artist_name, 
                                                       url=url,
                                                       roles=roles))


        return credited_artists
    
    def __update_tracks(self):
        new_credited_artists = list()

        for credited_artist in self.credited_artists:
            new_roles = list()

            for role in credited_artist.roles:
                new_tracks = list()
                
                if role.tracks:
                    for track in role.tracks:
                        if track in self.tracklist:
                            track.credited_artists = credited_artist
                            new_tracks.append(track)
                            self.tracklist[self.tracklist.index(track)] = track
                    
                    role.tracks = new_tracks
                
                new_roles.append(role)

            credited_artist.roles = new_roles
            new_credited_artists.append(credited_artist)
        
        self.credited_artists = new_credited_artists
    
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
        
    def _fetch_issue_info(self, issue):
        def get_release_date(elem):
                if not elem:
                    return None
                
                date_components_count = elem["title"].count(" ") + 1
                date_formating = {1: "%Y",
                                2: "%B %Y",
                                3: "%d %B %Y"}
                
                return datetime.strptime(elem["title"], date_formating[date_components_count])
        
        release_date = get_release_date(issue.find("issue_year"))

        if label_elem := issue.find(class_="label"):
            label = SimpleLabel(name=label_elem.text,
                                url=ROOT_URL + label_elem["href"])
            issue_number = label_elem.next_sibling.text.replace("/","").strip()
        else:
            label = issue_number = None

        countries = None
        if countries_elem:= issue.find("issue_countries"):
            countries = [country["title"] for country in countries_elem.find_all(class_="ui_flag")]

        title = issue.find("a")["title"]
        url = issue.find("a")["href"]
        format = issue.find(class_="issue_formats")["title"]
        attributes = issue.find(class_="attribute").text.split(", ") if issue.find(class_="attribute") else None

        return {
            "title": title,
            "url": url,
            "release_date": release_date,
            "format": format,
            "label": label,
            "issue_number": issue_number,
            "attributes": attributes,
            "countries": countries
            }
            

    def _fetch_issues(self):
        issues_elems = self._soup.find_all(class_="issue_info")
        issues_elems = [issue for issue in issues_elems if "release_view" not in issue["class"]]
        
        release_issues_list = list()

        for issue in issues_elems:
            issue_info = self._fetch_issue_info(issue)

            release_issue = SimpleReleaseIssue(
                title=issue_info["title"],
                url=issue_info["url"],
                release_date=issue_info["release_date"],
                format=issue_info["format"],
                label=issue_info["label"],
                issue_number=issue_info["issue_number"],
                attributes=issue_info["attributes"],
                countries=issue_info["countries"]
            )
            
            release_issues_list.append(release_issue)

        return release_issues_list

    def _fetch_is_nazi(self):
        if warning_div := self._soup.find(class_="warning"):
            return "Nazi" in warning_div.text
        
    def __str__(self):
        return self.title

    def __repr__(self):
        return f"{self.type}: {','.join([artist.name for artist in self.artists])} - {self.title}"

    def __eq__(self, other):
        return self.url == other.url
    
class ReleaseIssue(Release):
    def __init__(self, url) -> None:
        super().__init__(url=url)
        issue_elem = self._fetch_issue_elem()
        issue_info = self._fetch_issue_info(issue_elem)
        self.format = issue_info["format"]
        self.label = issue_info["label"]
        self.issue_number = issue_info["issue_number"]
        self.attributes = issue_info["attributes"]
        self.countries = issue_info["countries"]

    def _fetch_issue_elem(self):
        issues_elems = self._soup.find_all(class_="issue_info")[1:]

        for issue in issues_elems:
            if (ROOT_URL + issue.find("a")["href"]) == self.url:
                return issue

class User:
    def __init__(self, *, username=None, url=None) -> None:
        self.username = username or re.search(r"[\w+|_]+$", url).group()
        if not self.username:
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
                             url=ROOT_URL + artist_elem["href"])
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
        
class RYMList(EntryCollection):
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
        entries = [SimpleRYMList() for entry in list_elem[:-1:2]]
        
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
    def __init__(self, *, title=None, name=None, release_date=None, average_rating=None, number_of_ratings=None, number_of_reviews=None, url=None, cover=None, artist_name=None, artists=None, bolded=None):
        super().__init__(name=name or title, url=url)
        self.artist_name = artist_name
        self.artists = artists
        self.release_date = release_date
        self.average_rating = average_rating
        self.number_of_ratings = number_of_ratings
        self.number_of_reviews = number_of_reviews
        self.cover = cover
        self.is_bolded = bolded

    def get_release(self):
        return Release(self.url)
    
class SimpleRYMList(SimpleEntity):
    def __init__(self, *, name=None, title=None, url=None, author=None) -> None:
        super().__init__(name=name, title=title, url=url)
        self.author = author

    def get_list(self):
        return RYMList(self.url)
    
class SimpleUser(SimpleEntity):
    def get_user(self):
        return User(username=self.name, url=self.url)
    
class SimpleReleaseIssue(SimpleEntity):
    def __init__(self, *, title, url, format, release_date, label=None, issue_number=None, attributes=None, countries=None) -> None:
        super().__init__(title= title, url=url)
        self.format = format
        self.release_date = release_date
        self.label = label
        self.issue_number = issue_number
        self.attributes = attributes
        self.countries = countries

    def get_release_issue(self):
        return ReleaseIssue(self.url)
    
class SimpleLabel(SimpleEntity):
    def get_label(self):
        return Label(self.url)
    
class SimpleDistributor(SimpleEntity):
    def __init__(self, *, name=None, title=None, url=None, years=None) -> None:
        super().__init__(name=name, title=title, url=url)
        if years:
            self.years = years

    def get_distributor(self):
        return Distributor(self.url)
    
class LabelDistributor(SimpleLabel):
    def __init__(self, *, name=None, title=None, url=None, years=None) -> None:
        super().__init__(name=name, title=title, url=url)
        self.years = years

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