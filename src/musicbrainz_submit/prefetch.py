import io
import urllib.request
from multiprocessing.pool import ThreadPool
from queue import Queue
from typing import Optional

from PIL import Image
from PIL.ImageFile import ImageFile

from musicbrainz_submit.constants import USER_AGENT
from musicbrainz_submit.providers.provider import Provider, Album


def load_thumbnail(url: str | ImageFile) -> Optional[ImageFile]:
    if isinstance(url, ImageFile):
        return url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
        im = Image.open(io.BytesIO(data))
        im.thumbnail((120, 120))
        return im
    except:
        return None


def thumbnail_worker(items: tuple[Album, Queue]):
    album, queue = items
    if album.thumbnail is not None:
        album.thumbnail = load_thumbnail(album.thumbnail)
    queue.put("Thumbnails")


def prefetch_provider(
    input: tuple[type[Provider], list[str], Queue[str | tuple[str, int]]],
) -> Provider:
    provider_cls, links, queue = input
    provider = provider_cls()
    provider.message_queue = queue
    for url in links:
        provider.albums.extend(provider.fetch(url))
    queue.put(("Thumbnails", len(provider.albums)))
    # Only one at a time for better success rates, and this is usually not a bottleneck
    for album in provider.albums:
        if album.thumbnail is not None:
            album.thumbnail = load_thumbnail(album.thumbnail)
        queue.put("Thumbnails")
    return provider
