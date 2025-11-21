from pathlib import Path
from typing import List, Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.cache_handler import CacheFileHandler

from mbmc.cache import cached
from mbmc.music_brainz import normalize_url
from mbmc.providers._mb_link_types import (
    ARTIST_FREE_STREAMING,
    RELEASE_FREE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, Track, ArtistFormat
from mbmc.util import CONFIG_DIR

SESSION_FILE: Path = CONFIG_DIR / "spotify-session.txt"


class SpotifyProvider(Provider):
    def __init__(self):
        super().__init__("Spotify")
        cache_handler = CacheFileHandler(cache_path=str(SESSION_FILE))
        auth_manager = SpotifyClientCredentials(cache_handler=cache_handler)
        self.client = spotipy.Spotify(auth_manager=auth_manager)

    @staticmethod
    def item_to_artist(item: dict) -> ArtistFormat:
        return list(
            (artist["name"], normalize_url(artist["external_urls"]["spotify"]))
            for artist in item["artists"]
        )

    @cached
    def get_album(self, album_id: str) -> Album:
        album = self.client.album(album_id)
        tracks = [
            Track(
                title=track["name"],
                artist=SpotifyProvider.item_to_artist(track),
                duration=track["duration_ms"],
                track_nr=track["track_number"],
                disk_nr=track["disc_number"],
                provider=self,
            )
            for track in self.client.album_tracks(album["id"])["items"]
        ]
        album = self.client.album(album["id"])
        return Album(
            title=album["name"],
            artist=SpotifyProvider.item_to_artist(album),
            release_date=album["release_date"],
            tracks=tracks,
            url=normalize_url(album["external_urls"]["spotify"]),
            thumbnail=album["images"][0]["url"] if album["images"] else None,
            upn=album.get("external_ids", {}).get("upc"),
            provider=self,
        )

    def fetch(self, url: str, ignore: list[str]) -> list[Album]:
        finalized: list[Album] = []
        last_response = self.client.artist_albums(url.split("/")[-1], limit=50)
        raw_items = last_response["items"]
        while last_response["next"]:
            last_response = self.client.next(last_response)
            raw_items.extend(last_response["items"])
        self.set_total_items(len(raw_items))
        for album in raw_items:
            if normalize_url(album["external_urls"]["spotify"]) in ignore:
                self.finish_item()
                continue
            album = self.get_album(album["id"])
            album.provider = self
            for track in album.tracks:
                track.provider = self
            finalized.append(album)
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "open.spotify.com/artist/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_FREE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_FREE_STREAMING]
