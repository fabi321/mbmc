import re
from enum import Enum
from typing import List

import bandcamp_lib as bc
import requests

from mbmc.music_brainz import normalize_url
from mbmc.providers._mb_link_types import (
    ARTIST_BANDCAMP,
    RELEASE_DOWNLOAD_FOR_FREE,
    RELEASE_PURCHASE_FOR_DOWNLOAD,
    RELEASE_FREE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, Track


class AlbumType(Enum):
    Streamable = "streamable"
    Downloadable = "downloadable"
    Purchasable = "purchasable"


class BandcampProvider(Provider):
    def __init__(self) -> None:
        super().__init__("Bandcamp")
        self.status: dict[str, AlbumType] = {}

    def fetch(self, url: str) -> list[Album]:
        artist: bc.Artist = bc.artist_from_url_sync(url)
        finalized: list[Album] = []
        self.set_total_items(len(artist.discography))
        for album_entry in artist.discography:
            if album_entry.item_type == bc.ArtistDiscographyEntryType.Album:
                album = bc.fetch_album_sync(album_entry.band_id, album_entry.id)
            else:
                album = bc.fetch_track_sync(album_entry.band_id, album_entry.id)
            artist_name = [
                (
                    name.strip(),
                    (
                        normalize_url(artist.url)
                        if name.strip().lower() in artist.name.lower()
                        else "unknown"
                    ),
                )
                for name in (album_entry.artist_name or artist.name).split(",")
            ]
            tracks = [
                Track(
                    title=track.title,
                    artist=artist_name,
                    duration=int(track.duration * 1000),
                    track_nr=track.track_number or 1,  # Singles have no track number
                    provider=self,
                )
                for track in album.tracks
            ]
            if len(tracks) == 1:
                # Bandcamp sometimes spits out interesting track numbers for singles, see
                # https://ranarvegr.bandcamp.com/track/ko-lga-16
                tracks[0].track_nr = 1
            type_ = AlbumType.Purchasable
            if all(track.is_streamable for track in album.tracks):
                type_ = AlbumType.Streamable
            if album.free_download:
                type_ = AlbumType.Downloadable
            self.status[album.url] = type_
            genres: list[str] = []
            for tag in album.tags:
                if not tag.is_location:
                    genres.append(tag.normalized_name)
            req = requests.get(album.url)
            req.raise_for_status()
            page_content = req.text
            raw_upc = re.search(r"&quot;upc&quot;:&quot;([0-9]+)&quot;", page_content)
            upc = None
            if raw_upc:
                upc = raw_upc.group(1)
            finalized.append(
                Album(
                    title=album.title,
                    artist=artist_name,
                    release_date=f"{album.release_date:%Y-%m-%d}",
                    tracks=tracks,
                    url=normalize_url(album.url),
                    thumbnail=album.image.get_with_resolution(bc.ImageResolution.Px420),
                    genre=genres,
                    upn=upc,
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "bandcamp.com" in url

    def artist_url_types(self) -> List[str]:
        return [ARTIST_BANDCAMP]

    def url_types(self, album: Album) -> List[str]:
        match self.status[album.url]:
            case AlbumType.Streamable:
                return [RELEASE_FREE_STREAMING, RELEASE_PURCHASE_FOR_DOWNLOAD]
            case AlbumType.Downloadable:
                return [RELEASE_DOWNLOAD_FOR_FREE]
            case AlbumType.Purchasable:
                return [RELEASE_PURCHASE_FOR_DOWNLOAD]
            case _:
                raise NotImplementedError
