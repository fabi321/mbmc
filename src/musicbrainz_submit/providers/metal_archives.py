from typing import List

import requests
from bs4 import BeautifulSoup

from musicbrainz_submit.music_brainz import normalize_url
from musicbrainz_submit.providers._mb_link_types import (
    ARTIST_OTHER_DATABASES,
    RELEASE_OTHER_DATABASES,
)
from musicbrainz_submit.providers.provider import Provider, Album, Track, ArtistFormat


class MetalArchivesProvider(Provider):
    def __init__(self, ma_url: str, query: str):
        super().__init__("Metal Archives", query)
        self.ma_url: str = normalize_url(ma_url)
        self.artist_id: str = self.ma_url.split("/")[-1]

    def fetch(self) -> list[Album]:
        request = requests.get(
            f"https://www.metal-archives.com/band/discography/id/{self.artist_id}/tab/all"
        )
        request.raise_for_status()
        all_html = request.text
        finalized: list[Album] = []
        soup = BeautifulSoup(all_html, "html.parser")
        album_rows = soup.select("table tr")[1:]  # Skip header row
        for row in album_rows:
            cols = row.find_all("td")
            assert (
                len(cols) == 4
            ), "Unexpected number of columns in Metal Archives discography table"
            album_title = cols[0].get_text(strip=True)
            release_year = cols[2].get_text(strip=True)
            album_url = normalize_url(cols[0].find("a")["href"])
            release_type = cols[1].get_text(strip=True)
            finalized.append(
                Album(
                    title=album_title,
                    snippet=f"Released {release_year} ({release_type})",
                    url=album_url,
                    thumbnail=None,
                    provider=self,
                )
            )
        # In a real implementation, you would fetch data from Metal Archives here
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "metal-archives.com" in url and "/bands/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_OTHER_DATABASES]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_OTHER_DATABASES]
