from typing import List

from deezer import Client

from mbmc.music_brainz import normalize_url
from mbmc.providers._mb_link_types import (
    ARTIST_FREE_STREAMING,
    RELEASE_FREE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, Track


class DeezerProvider(Provider):
    def __init__(self):
        super().__init__("Deezer")
        self.client = Client()

    def fetch(self, url: str) -> list[Album]:
        artist = self.client.get_artist(int(url.split("/")[-1]))
        finalized: list[Album] = []
        raw_albums = list(artist.get_albums())
        self.set_total_items(len(raw_albums))
        for album in raw_albums:
            tracks = [
                Track(
                    title=track.title,
                    artist=[(track.artist.name, normalize_url(track.artist.link))],
                    duration=track.duration * 1000,
                    track_nr=track.track_position,
                    disk_nr=track.disk_number,
                    provider=self,
                )
                for track in album.get_tracks()
            ]
            finalized.append(
                Album(
                    title=album.title,
                    artist=[(album.artist.name, normalize_url(album.artist.link))],
                    release_date=f"{album.release_date:%Y-%m-%d}",
                    tracks=tracks,
                    url=normalize_url(album.link),
                    thumbnail=album.cover_medium,
                    genre=[genre.name.lower() for genre in album.genres],
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "deezer.com" in url and "/artist/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_FREE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_FREE_STREAMING]
