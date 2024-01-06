from ratelimit import limits, sleep_and_retry
from .exceptions import *
from .global_variables import *

class EntryCollection:
    @sleep_and_retry
    @limits(calls=CALL_LIMIT, period=RATE_LIMIT)
    def __init__(self, url, pages_class) -> None:
        self.init_url = url
        self.current_url = url
        self._cached_rym_response = requests.get(self.init_url, headers= HEADERS)
        if self._cached_rym_response.status_code != 200:
            raise RequestFailed(f"Initial request failed with status code {self._cached_rym_response.status_code}.")
        self._soup = bs4.BeautifulSoup(self._cached_rym_response.content, "html.parser")
        self.current_page = 1
        self.max_page = self._fetch_max_page(pages_class)
        if self.current_page > self.max_page:
            raise NoContent("This release has no lists.")
        self.entries = self._fetch_entries(init=True)

    def _fetch_max_page(self, pages_class):
        try:
            return int(self._soup.find_all("a", class_=pages_class)[-1].text)
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
        
        return self._specific_fetch()

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