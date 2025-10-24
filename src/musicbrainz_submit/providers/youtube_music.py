from functools import cache
from typing import List, Literal

import ytmusicapi

from musicbrainz_submit.music_brainz import normalize_url
from musicbrainz_submit.providers._mb_link_types import (
    ARTIST_YOUTUBE_MUSIC,
    RELEASE_FREE_STREAMING,
)
from musicbrainz_submit.providers.provider import Provider, Album, Track, ArtistFormat
import musicbrainz_submit.yt_music_api_types as types


class YouTubeMusicProvider(Provider):
    def __init__(self, youtube_url: str, query: str):
        super().__init__("YouTube Music", query)
        self.youtube_url: str = normalize_url(youtube_url)
        self.artist_id: str = self.youtube_url.split("/")[-1]
        self.client = ytmusicapi.YTMusic(location="NZ")

    def get_releases_for_artist(
        self, artist: types.Artist, type_: Literal["albums", "singles"]
    ) -> list[types.AlbumResult]:
        if type_ in artist:
            params: str = artist[type_].get("params")
            if params:
                param_result = self.client.get_artist_albums(
                    artist[type_]["browseId"], params
                )
                if param_result:
                    return param_result
            return artist[type_]["results"]
        return []

    @staticmethod
    def item_to_artist(item: types.Album | types.Track) -> ArtistFormat:
        return [
            (artist["name"], f'https://music.youtube.com/channel/{artist["id"]}')
            for artist in item["artists"]
        ]

    @cache
    def fetch(self) -> list[Album]:
        artist: types.Artist = self.client.get_artist(self.artist_id)
        finalized: list[Album] = []
        albums = self.get_releases_for_artist(artist, "albums")
        singles = self.get_releases_for_artist(artist, "singles")
        all_releases = albums + singles
        self.set_total_items(len(all_releases))
        for base_album in all_releases:
            album: types.Album = self.client.get_album(base_album["browseId"])
            tracks = [
                Track(
                    title=track["title"],
                    artist=YouTubeMusicProvider.item_to_artist(track),
                    duration=int(track["duration_seconds"] * 1000),
                    track_nr=track["trackNumber"],
                    provider=self,
                )
                for track in album["tracks"]
            ]
            finalized.append(
                Album(
                    title=album["title"],
                    artist=YouTubeMusicProvider.item_to_artist(album),
                    release_date=album.get("year", "Unknown"),
                    tracks=tracks,
                    snippet=f"By {', '.join(artist['name'] for artist in album['artists'])}, released {album.get('year', 'Unknown')}",
                    url=f"https://music.youtube.com/playlist?list={album['audioPlaylistId']}",
                    thumbnail=album.get("thumbnails", [{}])[-1].get("url", None),
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "music.youtube.com" in url and "/channel/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_FREE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_YOUTUBE_MUSIC]
