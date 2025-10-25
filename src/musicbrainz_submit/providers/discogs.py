from typing import List

import discogs_client
from discogs_client import Master

from musicbrainz_submit.constants import USER_AGENT
from musicbrainz_submit.music_brainz import normalize_url
from musicbrainz_submit.providers._mb_link_types import ARTIST_DISCOGS, RELEASE_DISCOGS
from musicbrainz_submit.providers.provider import Provider, Album, Track


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
    def item_to_artist(item) -> List[tuple[str, str]]:
        return [
            (
                artist.name,
                (
                    normalize_url(str(artist.url))
                    if artist.id != 194
                    else "https://www.discogs.com/artist/194"
                ),
            )
            for artist in item.artists
        ]

    def fetch(self, url: str) -> list[Album]:
        artist = self.client.artist(url.split("/")[-1])
        finalized: list[Album] = []
        self.set_total_items(len(artist.releases))
        for release in artist.releases:
            if isinstance(release, Master):
                continue
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
                        artist=DiscogsProvider.item_to_artist(track),
                        duration=duration,
                        track_nr=track_nr,
                        provider=self,
                    )
                )
            finalized.append(
                Album(
                    title=release.title,
                    artist=DiscogsProvider.item_to_artist(release),
                    release_date=str(release.year) if release.year else "Unknown",
                    tracks=tracks,
                    snippet=f"By {', '.join(artist.name for artist in release.artists)}, released {release.year if release.year else 'Unknown'}",
                    url=normalize_url(release.url),
                    thumbnail=release.data.get("thumb", None),
                    genre=[genre.lower() for genre in release.genres],
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "discogs.com/artist" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_DISCOGS]

    def artist_url_types(self) -> list[str]:
        return [ARTIST_DISCOGS]
