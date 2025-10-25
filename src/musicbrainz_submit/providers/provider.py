from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from queue import Queue
from typing import Optional, List, Any

from fuzzywuzzy import process
from transliterate import translit
from PIL.ImageFile import ImageFile
from transliterate.exceptions import LanguageDetectionError

ArtistFormat = str | list[str | tuple[str, str]]


@dataclass
class Track:
    provider: Provider
    title: str
    artist: ArtistFormat
    duration: int
    """duration in milliseconds"""
    track_nr: int
    disk_nr: int = 1


@dataclass
class Album:
    provider: Provider
    title: str
    snippet: str
    url: str
    artist: ArtistFormat
    release_date: str
    tracks: List[Track]
    thumbnail: Optional[str | ImageFile] = None
    genre: list[str] = field(default_factory=list)
    upn: Optional[int] = None
    extra_data: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    def __init__(self, name: str):
        self.name: str = name
        self.query: str = ""
        self.message_queue: Optional[Queue[str | tuple[str, int]]] = None
        self.albums: list[Album] = []

    def set_total_items(self, total: int) -> None:
        if self.message_queue is not None:
            self.message_queue.put((self.name, total))

    def finish_item(self) -> None:
        if self.message_queue is not None:
            self.message_queue.put(self.name)

    @abstractmethod
    def fetch(self, url: str) -> list[Album]:
        raise NotImplementedError

    @staticmethod
    def normalize_name(album: Album | str) -> str:
        if isinstance(album, Album):
            album = album.title
        try:
            album = translit(album, reversed=True)
        except LanguageDetectionError:
            pass
        return album.lower()

    def filter(self) -> list[Album]:
        """Determine if this provider should be used based on available data."""
        relevant = [album for album in self.albums if album.status == AlbumStatus.TODO]
        chosen = process.extractBests(
            self.query, relevant, score_cutoff=70, processor=Provider.normalize_name
        )
        return [album for album, _ in chosen]

    @staticmethod
    @abstractmethod
    def relevant(url: str) -> bool:
        """Check if the given URL is relevant for this provider."""
        raise NotImplementedError

    @abstractmethod
    def url_types(self, album: Album) -> List[str]:
        """Return a list of URL types that this provider can handle for the given album."""
        return self.artist_url_types()

    @abstractmethod
    def artist_url_types(self) -> List[str]:
        """Return a list of URL types that this provider can handle for artists."""
        raise NotImplementedError
