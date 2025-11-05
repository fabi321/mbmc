from typing import List

import discogs_client
from discogs_client import Master, Track as DCTrack, Release as DCRelease

from mbmc.cache import cached
from mbmc.constants import USER_AGENT
from mbmc.music_brainz import normalize_url
from mbmc.providers._mb_link_types import ARTIST_DISCOGS, RELEASE_DISCOGS
from mbmc.providers.provider import Provider, Album, Track


def minutes_to_milliseconds(minutes: str) -> int:
    parts = minutes.split(":")
    if len(parts) == 2:
        mins, secs = parts
        return (int(mins) * 60 + int(secs)) * 1000
    elif len(parts) == 3:
        hrs, mins, secs = parts
        return (int(hrs) * 3600 + int(mins) * 60 + int(secs)) * 1000
    return 0


class DiscogsProvider(Provider):
    def __init__(self):
        super().__init__("Discogs")
        self.client = discogs_client.Client(USER_AGENT)

    @staticmethod
    def item_to_artist(item: DCTrack | DCRelease) -> List[tuple[str, str]]:
        return [(artist.name, f"https://www.discogs.com/artist/{artist.id}") for artist in item.artists]

    @cached
    def get_release(self, release_id: str) -> Album:
        release = self.client.release(release_id)
        tracks = []
        for track in release.tracklist:
            track_nr = 0
            try:
                track_nr = int(track.position)
            except:
                pass
            duration = minutes_to_milliseconds(track.duration or "0:00")
            tracks.append(
                Track(
                    title=track.title,
                    artist=self.item_to_artist(track),
                    duration=duration,
                    track_nr=track_nr,
                    provider=self,
                )
            )
        return Album(
            title=release.title,
            artist=self.item_to_artist(release),
            release_date=str(release.year) if release.year else "Unknown",
            tracks=tracks,
            url=normalize_url(release.url),
            thumbnail=release.data.get("thumb", None),
            genre=[genre.lower() for genre in release.genres],
            provider=self,
        )

    def fetch(self, url: str) -> list[Album]:
        artist = self.client.artist(url.split("/")[-1])
        finalized: list[Album] = []
        self.set_total_items(len(artist.releases))
        for release in artist.releases:
            if isinstance(release, Master):
                self.finish_item()
                continue
            release = self.get_release(release.id)
            release.provider = self
            for track in release.tracks:
                track.provider = self
            finalized.append(release)
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "discogs.com/artist" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_DISCOGS]

    def artist_url_types(self) -> list[str]:
        return [ARTIST_DISCOGS]
