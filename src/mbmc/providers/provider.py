from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue
from typing import Optional, Any

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


class AlbumStatus(Enum):
    TODO = "To Do"
    COMPLETED = "Completed"
    IGNORED = "Ignored"
    BANNED = "Banned"


@dataclass
class Album:
    provider: Provider
    title: str
    url: str
    artist: ArtistFormat
    release_date: str
    tracks: list[Track]
    thumbnail: Optional[str | ImageFile] = None
    genre: list[str] = field(default_factory=list)
    upn: Optional[int] = None
    extra_data: dict[str, Any] = field(default_factory=dict)
    extra_info: Optional[str] = None
    status: AlbumStatus = AlbumStatus.TODO


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
        relevant = [album for album in self.albums if album.status == AlbumStatus.TODO or album.status == AlbumStatus.IGNORED]
        chosen = process.extractBests(
            self.query, relevant, score_cutoff=70, processor=Provider.normalize_name
        )
        return [album for album, _ in chosen]

    def get_todo_name(self) -> Optional[str]:
        for album in self.albums:
            if album.status == AlbumStatus.TODO:
                return album.title.lower().strip()
        return None

    def is_done(self, album: str) -> bool:
        found_done: bool = False
        found_todo: bool = False
        album = album.lower().strip()
        for a in self.albums:
            if a.title.lower().strip() == album:
                if a.status == AlbumStatus.TODO:
                    found_todo = True
                else:
                    found_done = True
        return found_done and not found_todo

    def ignore_album(self, album: str) -> None:
        album = album.lower().strip()
        for a in self.albums:
            if a.title.lower().strip() == album:
                a.status = AlbumStatus.IGNORED

    @staticmethod
    def format_artist_credit(artist: ArtistFormat) -> str:
        if isinstance(artist, str):
            return artist
        result: str = ""
        has_join_phrase: bool = True
        for entry in artist:
            if isinstance(entry, str):
                result += entry
                has_join_phrase = not has_join_phrase
            else:
                if not has_join_phrase:
                    result += ", "
                result += entry[0]
                has_join_phrase = False
        return result

    @staticmethod
    def format_snippet(album: Album) -> str:
        result: str = f"By {Provider.format_artist_credit(album.artist)}"
        if album.release_date:
            result += f", released {album.release_date}"
        result += f", {len(album.tracks)} tracks"
        if album.upn:
            result += f", UPN {album.upn}"
        if album.extra_info:
            result += f" {album.extra_info}"
        return result

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
