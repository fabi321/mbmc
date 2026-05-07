import hashlib
import re
from functools import cache
from typing import TypedDict, List, Literal
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

import requests
from bs4 import BeautifulSoup, Tag
from requests.cookies import RequestsCookieJar

from mbmc.providers._mb_link_types import (
    ARTIST_FREE_STREAMING,
    RELEASE_FREE_STREAMING,
)
from mbmc.providers.provider import Provider, Album, ArtistFormat, Track
from mbmc.cache import cached


class Playlist(TypedDict):
    owner_id: int
    id: int
    title: str
    description: str
    access_key: str


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


@cache
def get_oauth() -> tuple[str, str]:
    """
    request = requests.get("https://vk.com")
    request.raise_for_status()
    match = re.search(
        r"https://st.vk.com/dist/web/chunks/common.[0-9a-f]+.js",
        request.text
     )
    assert match
    common_url = match.group(0)
    request = requests.get(common_url)
    request.raise_for_status()
    client_secret = re.search(r'[a-zA-Z]="([a-zA-Z0-9]{20})"', request.text)
    assert client_secret
    raise NotImplementedError()
    """
    return ("6287487", "QbYic1K3lEV5kTGiqlq2")


@cache
def get_access_token() -> str:
    client_id, client_secret = get_oauth()
    request = requests.post(
        "https://login.vk.com/?act=get_anonym_token",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0"
        },
        data={
            "client_secret": client_secret,
            "client_id": client_id,
            "scopes": "audio_anonymous,video_anonymous,photos_anonymous,profile_anonymous",
            "isApiOauthAnonymEnabled": "false",
            "version": "1",
            "app_id": "6287487",
        },
        cookies=get_cookies(),
    )
    request.raise_for_status()
    content = request.json()
    assert content["type"] == "okay"
    return content["data"]["access_token"]


def vk_artist(obj: dict) -> ArtistFormat:
    result = []
    for artist in obj["main_artists"]:
        result.append((artist["name"], resolve_artist(artist["domain"])))
        result.append(", ")
    result.pop()
    if "featured_artists" in obj:
        result.append(" feat. ")
        for artist in obj["featured_artists"]:
            result.append((artist["name"], resolve_artist(artist["domain"])))
            result.append(", ")
        result.pop()
    return result


def api_call(path: str, data: dict) -> dict:
    client_id, _ = get_oauth()
    if "access_token" not in data:
        data["access_token"] = get_access_token()
    request = requests.post(
        f"https://api.vk.com/method/{path}?v=5.276&client_id={client_id}",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
            "Content-Type": "application/json",
        },
        data=data,
        cookies=get_cookies(),
    )
    request.raise_for_status()
    return request.json()["response"]


@cached
def resolve_artist(domain: str) -> str:
    response = api_call(
        "catalog.getAudioArtist",
        {
            "url": f"https://vk.com/artist/{domain}",
            "need_blocks": "1",
            "aritst_id": domain,
            "ref": ""
        }
    )
    result = response["artists"][0]["domain"]
    return f"https://vk.com/artist/{result}"


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

    def get_releases(
        self,
        artist_name: str,
        type_: Literal["albums", "singles"]
    ) -> list[Playlist]:
        response = api_call(
            "catalog.getAudioArtist",
            {
                "url": f"https://vk.com/artist/{artist_name}/{type_}",
                "need_blocks": "1",
                "artist_id": artist_name,
                "ref": ""
            }
        )
        return response["playlists"]

    @cached
    def get_album(self, owner_id: str, playlist_id: str, access_key: str) -> Album:
        client_id, _ = get_oauth()
        album_information = api_call(
            "audio.getPlaylistById",
            {
                "playlist_id": playlist_id,
                "owner_id": owner_id,
                "access_key": access_key,
                "extra_fields": "owner, duration",
            },
        )["playlist"]
        audios = api_call(
            "audio.getIdsBySource",
            {
                "entity_id": f"{owner_id}_{playlist_id}_{access_key}",
                "source": "playlist",
                "ref": "",
            },
        )
        audios = [i["audio_id"] for i in audios["audios"]]
        track_data = api_call(
            "audio.getById",
            {"audios": ",".join(audios)},
        )
        tracks = []
        for i, track in enumerate(track_data):
            duration = track.get("duration", None)
            if duration:
                duration *= 1000
            tracks.append(Track(
                provider=self,
                title=track["title"],
                artist=vk_artist(track),
                duration=duration,
                track_nr=i + 1,
            ))
        thumbnail = None
        max_res = None
        for key, value in album_information["photo"].items():
            if not key.startswith("photo_"):
                continue
            size = int(key.split("_")[1])
            if not max_res or max_res < size:
                max_res = size
                thumbnail = value
        return Album(
            provider=self,
            title=album_information["title"],
            url=f"https://vk.com/music/album/{owner_id}_{playlist_id}",
            artist=vk_artist(album_information),
            release_date=str(album_information["year"]),
            tracks=tracks,
            thumbnail=thumbnail,
            genre=[i["name"] for i in album_information["genres"]],
        )

    def fetch(self, url: str, ignore: list[str]) -> list[Album]:
        artist_name: str = url.split("/")[-1]
        albums = self.get_releases(artist_name, "albums")
        albums.extend(self.get_releases(artist_name, "singles"))
        finalized: list[Album] = []
        self.set_total_items(len(albums))
        for album in albums:
            if f"https://vk.com/music/album/{album['owner_id']}_{album['id']}" in ignore:
                self.finish_item()
                continue
            album = self.get_album(str(album["owner_id"]), str(album["id"]), album["access_key"])
            album.provider = self
            for track in album.tracks:
                track.provider = self
            finalized.append(album)
            """
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
            """
            self.finish_item()
        return finalized

    @staticmethod
    def relevant(url: str) -> bool:
        return "vk.com/artist" in url

    def url_types(self, album: Album) -> List[str]:
        return [RELEASE_FREE_STREAMING]

    def artist_url_types(self) -> List[str]:
        return [ARTIST_FREE_STREAMING]
