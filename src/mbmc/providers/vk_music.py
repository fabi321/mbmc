import json
import re
from typing import TypedDict, List

import requests
from bs4 import BeautifulSoup, Tag

from mbmc.music_brainz import normalize_url
from mbmc.providers._mb_link_types import (
    ARTIST_FREE_STREAMING,
    RELEASE_FREE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, ArtistFormat


class Playlist(TypedDict):
    ownerId: int
    id: int
    title: str
    description: str
    authorLine: str
    """Name including hrefs"""
    authorName: str
    """Human readable name"""
    coverUrl: str


def get_data(artist_name: str, type_: str) -> list[Playlist]:
    request = requests.get(
        f"https://vk.com/artist/{artist_name}/{type_}",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0"
        },
    )
    request.raise_for_status()
    all_html = request.text
    section_id = next(re.finditer(r'"sectionId":"([^"]*)"', all_html)).group(1)
    request = requests.post(
        f"https://vk.com/audio?act=load_catalog_section",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"al": "1", "section_id": section_id},
    )
    request.raise_for_status()
    text = request.text.replace("<!--", "", 1)
    return json.loads(text)["payload"][1][1]["playlists"]


class VkMusicProvider(Provider):
    def __init__(self):
        super().__init__("VK Music")

    @staticmethod
    def author_line_to_artist(author_line: str) -> ArtistFormat:
        result = []
        soup = BeautifulSoup(author_line, "html.parser")
        for child in soup.children:
            if isinstance(child, str):
                result.append(child)
            else:
                assert isinstance(child, Tag)
                assert child.name == "a"
                result.append((child.text, child["href"]))
        return result

    def fetch(self, url: str) -> list[Album]:
        artist_name: str = url.split("/")[-1]
        albums = get_data(artist_name, "albums")
        albums.extend(get_data(artist_name, "singles"))
        finalized: list[Album] = []
        self.set_total_items(len(albums))
        for album in albums:
            finalized.append(
                Album(
                    title=album["title"],
                    artist=VkMusicProvider.author_line_to_artist(album["authorLine"]),
                    release_date="",
                    tracks=[],
                    snippet=f"By {album['authorName']}",
                    url=f"https://vk.com/music/album/{album['ownerId']}_{album['id']}",
                    thumbnail=album["coverUrl"],
                    provider=self,
                )
            )
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "vk.com/artist" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_FREE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_FREE_STREAMING]
