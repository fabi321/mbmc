import datetime
import re
from functools import cache
from typing import List

import requests
from bs4 import BeautifulSoup
import applemusicpy

from mbmc.cache import cached
from mbmc.music_brainz import normalize_url
from mbmc.providers._mb_link_types import (
    ARTIST_STREAMING,
    RELEASE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, Track, ArtistFormat


@cache
def get_api_key() -> str:
    initial: str = requests.get("https://music.apple.com/us/search?term=beatles").text
    soup = BeautifulSoup(initial, "html.parser")
    results = soup.find_all("script", attrs={"type": "module", "crossorigin": True})
    assert len(results) == 1
    script_url = results[0]["src"]
    script = requests.get(f"https://music.apple.com{script_url}").text
    match = re.search(r'const\s+[a-z]+\s*=\s*"(ey.+?)"', script)
    assert match is not None
    return match.group(1)


class PatchedAppleMusicClient(applemusicpy.AppleMusic):
    def generate_token(self, session_length):
        self.token_valid_until = datetime.datetime.now() + datetime.timedelta(
            hours=session_length
        )
        self.token_str = get_api_key()

    def _auth_headers(self):
        self.root = "https://amp-api.music.apple.com/v1/"
        headers = super()._auth_headers()
        headers["Origin"] = "https://music.apple.com"
        return headers

    def artist(self, artist_id, storefront="us", l=None, include=None):
        return self._get_resource(
            artist_id,
            "artists",
            storefront=storefront,
            l=l,
            include=include,
            views="appears-on-albums,full-albums,live-albums,singles",
        )

    def album(self, album_id, storefront="us", l=None, include=None):
        return self._get_resource(
            album_id,
            "albums",
            storefront=storefront,
            l=l,
            **{
                "fields[artists]": "name,url",
                "format[resources]": "map",
                "include": "artists",
                "include[songs]": "artists,composers,albums",
            },
        )

    def collect_items(self, item) -> list:
        results = [i["attributes"] for i in item["data"]]
        current_item: dict = item
        while "next" in current_item:
            current_item = self._get(self.root.rsplit("/", 2)[0] + current_item["next"])
            results.extend(i["attributes"] for i in current_item["data"])
        return results


class AppleMusicProvider(Provider):
    def __init__(self):
        super().__init__("Apple Music")
        self.client = PatchedAppleMusicClient("x", "y", "z")

    @staticmethod
    def item_to_artist(item: dict, root: dict) -> ArtistFormat:
        artists = []
        for artist in item["relationships"]["artists"]["data"]:
            artist = root["artists"][artist["id"]]["attributes"]
            artists.append((artist["name"], normalize_url(artist["url"])))
        return artists

    @cached
    def get_album(self, album_id: str) -> Album:
        resources = self.client.album(album_id)["resources"]
        tracks = [
            Track(
                title=track["attributes"]["name"],
                artist=AppleMusicProvider.item_to_artist(track, resources),
                duration=track["attributes"].get("durationInMillis"),
                track_nr=track["attributes"]["trackNumber"],
                disk_nr=track["attributes"].get("discNumber", 1),
                provider=self,
            )
            for track in resources["songs"].values()
        ]
        tracks.sort(key=lambda x: (x.disk_nr, x.track_nr))
        _, album = resources["albums"].popitem()
        genres: list[str] = album["attributes"].get("genreNames", [])
        genres = [genre.lower() for genre in genres]
        if "music" in genres:
            genres.remove("music")
        return Album(
            title=album["attributes"]["name"]
            .replace(" - EP", "")
            .replace(" - Single", ""),
            artist=AppleMusicProvider.item_to_artist(album, resources),
            release_date=album["attributes"]["releaseDate"],
            tracks=tracks,
            upn=album["attributes"].get("upc", None),
            url=f"https://music.apple.com/album/{album_id}",
            thumbnail=album["attributes"]["artwork"]["url"].replace(
                "{w}x{h}", "640x640"
            ),
            genre=genres,
            provider=self,
        )

    def fetch(self, url: str, ignore: list[str]) -> list[Album]:
        artist = self.client.artist(url.split("/")[-1])
        artist: dict = artist["data"][0]
        albums = self.client.collect_items(artist["views"]["full-albums"])
        albums.extend(self.client.collect_items(artist["views"]["appears-on-albums"]))
        albums.extend(self.client.collect_items(artist["views"]["live-albums"]))
        albums.extend(self.client.collect_items(artist["views"]["singles"]))
        finalized: list[Album] = []
        self.set_total_items(len(albums))
        for base_album in albums:
            if normalize_url(base_album["url"]) in ignore:
                self.finish_item()
                continue
            album = self.get_album(base_album["url"].split("/")[-1])
            album.provider = self
            for track in album.tracks:
                track.provider = self
            finalized.append(album)
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "music.apple.com" in url and "/artist/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_STREAMING]

    def artist_url_types(self) -> list[str]:
        return [ARTIST_STREAMING]
