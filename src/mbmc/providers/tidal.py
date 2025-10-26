from pathlib import Path
from typing import List

import tidalapi

from mbmc.providers._mb_link_types import (
    ARTIST_STREAMING,
    RELEASE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, Track, ArtistFormat
from mbmc.util import CONFIG_DIR

SESSION_FILE: Path = CONFIG_DIR / "tidal-session.txt"


class TidalProvider(Provider):
    def __init__(self):
        super().__init__("Tidal")
        self.session = tidalapi.Session()
        try:
            self.session.load_session_from_file(SESSION_FILE)
            if not self.session.check_login():
                self.session.login_oauth_simple()
        except Exception:
            self.session.login_oauth_simple()
        self.session.save_session_to_file(SESSION_FILE)

    @staticmethod
    def item_to_artist(item: tidalapi.Album | tidalapi.Track) -> ArtistFormat:
        if item.artists:
            return [
                (artist.name, f"https://tidal.com/artist/{artist.id}")
                for artist in item.artists
            ]
        return item.artist.name

    def fetch(self, url: str) -> list[Album]:
        artist = self.session.artist(url.split("/")[-1])
        finalized: list[Album] = []
        raw_albums = artist.get_albums() + artist.get_other() + artist.get_ep_singles()
        self.set_total_items(len(raw_albums))
        for album in raw_albums:
            artist_name = album.artist
            if album.artists:
                artist_name = ", ".join(artist.name for artist in album.artists)
            tracks = [
                Track(
                    title=track.name,
                    artist=TidalProvider.item_to_artist(track),
                    duration=int(track.duration * 1000),
                    track_nr=track.track_num,
                    provider=self,
                )
                for track in album.tracks()
            ]
            finalized.append(
                Album(
                    title=album.name,
                    artist=TidalProvider.item_to_artist(album),
                    release_date=f"{album.release_date:%Y-%m-%d}",
                    tracks=tracks,
                    upn=album.universal_product_number,
                    snippet=f"By {artist_name}, released {album.release_date:%Y-%m-%d}",
                    url=f"https://tidal.com/album/{album.id}",
                    thumbnail=album.image(640),
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "tidal.com" in url and "/artist/" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_STREAMING]
