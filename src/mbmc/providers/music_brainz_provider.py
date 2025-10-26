from typing import List

import musicbrainzngs as mb

from mbmc.music_brainz import get_releases
from mbmc.providers.provider import Provider, Album, Track


class MusicBrainzProvider(Provider):
    def __init__(self):
        super().__init__("MusicBrainz")

    def fetch(self, url: str) -> list[Album]:
        releases = get_releases(url.split("/")[-1])
        finalized: list[Album] = []
        self.set_total_items(len(releases))
        for release in releases:
            tracks = [
                Track(
                    title=track["recording"]["title"],
                    artist=track["recording"]["artist-credit-phrase"],
                    duration=int(track.get("length", 0)),
                    track_nr=int(track["position"]),
                    provider=self,
                )
                for track in release["medium-list"][0]["track-list"]
            ]
            thumbnail = None
            try:
                cover_art = mb.get_image_list(release["id"])
                for cover in cover_art["images"]:
                    if cover.get("front", False):
                        thumbnail = cover.get("thumbnails", {}).get("small", None)
                        break
            except:
                pass
            finalized.append(
                Album(
                    title=release["title"],
                    snippet=f"By {release['artist-credit-phrase']}",
                    url=f"https://musicbrainz.org/release/{release['id']}",
                    artist=release["artist-credit-phrase"],
                    release_date=release.get("date", "Unknown"),
                    tracks=tracks,
                    extra_data={"mbid": release["id"]},
                    thumbnail=thumbnail,
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "musicbrainz.org/artist/" in url

    def url_types(self, album: Album) -> List[str]:
        return []

    def artist_url_types(self) -> List[str]:
        return []
