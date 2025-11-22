import hashlib
import json
import re
from functools import cache
from typing import TypedDict, List
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

import requests
from bs4 import BeautifulSoup, Tag
from requests.cookies import RequestsCookieJar

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


@cache
def get_cookies() -> RequestsCookieJar:
    request = requests.get(
        "https://vk.com/challenge.html",
        allow_redirects=True,
    )
    request.raise_for_status()
    codes: list[str] = re.search(r"var codes = \[(.*?)];var", request.text).group(1)[1:-1].split("],[")
    salt: str = ''
    for code in codes:
        init: int = int(re.search(r"return ([0-9-]+);", code).group(1))
        for mutation in reversed(re.findall(r"\(function\(e\) ?\{(.*?)}\),", code)):
            if "return e" in mutation:
                parts = re.search(r"return e ?([-+^]) ?([0-9-]+);", mutation)
                if parts is None:
                    raise RuntimeError(f"Couldn't parse {mutation}")
                operator = parts.group(1)
                operand = int(parts.group(2))
                if operator == "+":
                    init += operand
                elif operator == "-":
                    init -= operand
                elif operator == "^":
                    init ^= operand
            else:
                for possibility in re.finditer(r'"([0-9-]+)":([0-9-]+)', mutation):
                    if possibility.group(1) == str(init):
                        init = int(possibility.group(2))
                        break
                else:
                    raise ValueError("Could not find matching mutation")
        salt += chr(init)
    url = urlparse(request.url)
    query = parse_qs(url.query)
    hash429 = query.get("hash429")[0]
    key = hashlib.md5(f"{hash429}:{salt}".encode()).hexdigest()
    query["key"] = [key]
    new_url = urlunparse(
        (url.scheme, url.netloc, url.path, url.params, urlencode(query, doseq=True), url.fragment)
    )
    result = requests.get(new_url, allow_redirects=True)
    result.raise_for_status()
    return result.cookies


def get_data(artist_name: str, type_: str) -> list[Playlist]:
    request = requests.get(
        f"https://vk.com/artist/{artist_name}/{type_}",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0"
        },
        cookies=get_cookies(),
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
        cookies=get_cookies(),
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

    def fetch(self, url: str, ignore: list[str]) -> list[Album]:
        artist_name: str = url.split("/")[-1]
        albums = get_data(artist_name, "albums")
        albums.extend(get_data(artist_name, "singles"))
        finalized: list[Album] = []
        self.set_total_items(len(albums))
        for album in albums:
            if f"https://vk.com/music/album/{album['ownerId']}_{album['id']}" in ignore:
                self.finish_item()
                continue
            finalized.append(
                Album(
                    title=album["title"],
                    artist=VkMusicProvider.author_line_to_artist(album["authorLine"]),
                    release_date="",
                    tracks=[],
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
