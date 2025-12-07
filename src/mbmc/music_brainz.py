import re
from functools import cache
from typing import Optional

import musicbrainzngs as mb

from mbmc.constants import USER_AGENT

mb.set_useragent(*USER_AGENT.split("/"))

MATCHED_URLS: dict[str, Optional[str]] = {}


def normalize_url(url: str) -> str:
    if "youtube.com" not in url:
        url = url.strip().split("?")[0]
    url = url.rstrip("/")
    if "music.apple.com" in url:
        # Remove specific country code
        url = re.sub(r"(music.apple.com/)[a-z]{2}/", r"\1", url)
        url = re.sub(
            r"(music.apple.com/(?:album|artist|song)/)[^/]+/([0-9])", r"\1\2", url
        )
    elif "discogs.com" in url:
        url = url.split("-")[0]
    return url


def find_url(url: str) -> Optional[str]:
    if url in MATCHED_URLS:
        return MATCHED_URLS[url]
    if url.startswith("https://musicbrainz.org/artist/"):
        mb_id = url.split("/")[-1]
        MATCHED_URLS[normalize_url(url)] = mb_id
        return mb_id
    try:
        result = mb.browse_urls(url, includes=["artist-rels", "release-rels"])
    except mb.ResponseError:
        result = None
    target: Optional[str] = None
    if result:
        artists = result['url'].get("artist-relation-list", [])
        if len(artists) == 1:
            target = artists[0]["artist"]["id"]
        releases = result['url'].get("release-relation-list", [])
        if len(releases) == 1:
            target = releases[0]["release"]["id"]
    MATCHED_URLS[normalize_url(url)] = target
    return target


def inner_get_releases(mb_id: str, various_artists: bool) -> list[dict]:
    releases = []
    limit = 100
    offset = 0
    extra = {"track_artist": mb_id} if various_artists else {"artist": mb_id}

    while True:
        result = mb.browse_releases(
            **extra,
            includes=[
                "recordings",
                "url-rels",
                "recording-rels",
                "release-rels",
                "media",
                "artist-credits",
            ],
            limit=limit,
            offset=offset,
        )
        batch = result.get("release-list", [])
        releases.extend(batch)
        if len(releases) >= result["release-count"]:
            break
        offset += len(batch)
    return releases


@cache
def get_releases(mb_id: str) -> list[dict]:
    releases = inner_get_releases(mb_id, various_artists=False)
    releases.extend(inner_get_releases(mb_id, various_artists=True))

    for release in releases:
        for url in release.get("url-relation-list", []):
            MATCHED_URLS[normalize_url(url["target"])] = release["id"]

    return releases


@cache
def get_artist(mb_id: str) -> dict:
    artist = mb.get_artist_by_id(mb_id, includes=["url-rels", "release-groups"])[
        "artist"
    ]
    for url in artist.get("url-relation-list", []):
        MATCHED_URLS[normalize_url(url["target"])] = artist["id"]
    return artist
