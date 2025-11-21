from typing import List, Optional

import musicbrainzngs as mb

from mbmc.cache import cached
from mbmc.music_brainz import get_releases
from mbmc.providers.provider import Provider, Album, Track


@cached
def get_cover_art(mb_id: str) -> Optional[str]:
    try:
        cover_art = mb.get_image_list(mb_id)
        for cover in cover_art["images"]:
            if cover.get("front", False):
                return cover.get("thumbnails", {}).get("small", None)
    except:
        return None
    return None


class MusicBrainzProvider(Provider):
    def __init__(self):
        super().__init__("MusicBrainz")

    def fetch(self, url: str, _ignore: list[str]) -> list[Album]:
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
            thumbnail = get_cover_art(release["id"])
            extra_info: Optional[str] = None
            if len(release["medium-list"]) >= 1:
                extra_info = f"({release['medium-list'][0].get('format', 'Unknown Format')})"
            finalized.append(
                Album(
                    title=release["title"],
                    url=f"https://musicbrainz.org/release/{release['id']}",
                    artist=release["artist-credit-phrase"],
                    release_date=release.get("date", "Unknown"),
                    tracks=tracks,
                    extra_data={"mbid": release["id"], "release_country": release.get("country", None)},
                    thumbnail=thumbnail,
                    upn=release.get("barcode", None),
                    extra_info=extra_info,
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
