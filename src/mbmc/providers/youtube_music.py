from typing import List, Literal

import ytmusicapi

from mbmc.cache import cached
from mbmc.providers._mb_link_types import (
    ARTIST_YOUTUBE_MUSIC,
    RELEASE_FREE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, Track, ArtistFormat
import mbmc.yt_music_api_types as types


class YouTubeMusicProvider(Provider):
    def __init__(self):
        super().__init__("YouTube Music")
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

    @cached
    def get_album(self, browse_id: str) -> Album:
        album: types.Album = self.client.get_album(browse_id)
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
        return Album(
            title=album["title"],
            artist=YouTubeMusicProvider.item_to_artist(album),
            release_date=album.get("year", "Unknown"),
            tracks=tracks,
            url=f"https://music.youtube.com/playlist?list={album['audioPlaylistId']}",
            thumbnail=album.get("thumbnails", [{}])[-1].get("url", None),
            provider=self,
        )

    def fetch(self, url: str) -> list[Album]:
        artist: types.Artist = self.client.get_artist(url.split("/")[-1])
        finalized: list[Album] = []
        albums = self.get_releases_for_artist(artist, "albums")
        singles = self.get_releases_for_artist(artist, "singles")
        all_releases = albums + singles
        self.set_total_items(len(all_releases))
        for base_album in all_releases:
            album = self.get_album(base_album["browseId"])
            album.provider = self
            for track in album.tracks:
                track.provider = self
            finalized.append(album)
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "music.youtube.com" in url and "/channel/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_FREE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_YOUTUBE_MUSIC]
