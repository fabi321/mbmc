from functools import cache
from pathlib import Path
from typing import List

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.cache_handler import CacheFileHandler

from musicbrainz_submit.music_brainz import normalize_url
from musicbrainz_submit.providers._mb_link_types import (
    ARTIST_FREE_STREAMING,
    RELEASE_FREE_STREAMING,
)
from musicbrainz_submit.providers.provider import Provider, Album, Track, ArtistFormat
from musicbrainz_submit.util import CONFIG_DIR

SESSION_FILE: Path = CONFIG_DIR / "spotify-session.txt"


class SpotifyProvider(Provider):
    def __init__(self, spotify_url: str, query: str):
        super().__init__("Spotify", query)
        self.spotify_url: str = normalize_url(spotify_url)
        self.artist_id = self.spotify_url.split("/")[-1]
        cache_handler = CacheFileHandler(cache_path=str(SESSION_FILE))
        auth_manager = SpotifyClientCredentials(cache_handler=cache_handler)
        self.client = spotipy.Spotify(auth_manager=auth_manager)

    @staticmethod
    def item_to_artist(item: dict) -> ArtistFormat:
        return list(
            (artist["name"], normalize_url(artist["external_urls"]["spotify"]))
            for artist in item["artists"]
        )

    @cache
    def fetch(self) -> list[Album]:
        finalized: list[Album] = []
        last_response = self.client.artist_albums(self.artist_id, limit=50)
        raw_items = last_response["items"]
        while last_response["next"]:
            last_response = self.client.next(last_response)
            raw_items.extend(last_response["items"])
        self.set_total_items(len(raw_items))
        for album in raw_items:
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
            finalized.append(
                Album(
                    title=album["name"],
                    artist=SpotifyProvider.item_to_artist(album),
                    release_date=album["release_date"],
                    tracks=tracks,
                    snippet=f"By {', '.join(artist['name'] for artist in album['artists'])}, released {album['release_date']}",
                    url=normalize_url(album["external_urls"]["spotify"]),
                    thumbnail=album["images"][0]["url"] if album["images"] else None,
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "open.spotify.com/artist/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_FREE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_FREE_STREAMING]
