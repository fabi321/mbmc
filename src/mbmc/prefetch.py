import io
import urllib.request
from queue import Queue
from typing import Optional

from PIL import Image
from PIL.ImageFile import ImageFile
from time import sleep

from mbmc.cache import cached
from mbmc.constants import USER_AGENT
from mbmc.providers.provider import Provider, Album


@cached
def get_thumbnail(url: str) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
        return data
    except:
        sleep(1)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            return data
        except:
            return None



def load_thumbnail(url: str | ImageFile) -> Optional[ImageFile]:
    if isinstance(url, ImageFile):
        return url
    try:
        data = get_thumbnail(url)
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
    input: tuple[type[Provider], set[str], Queue[str | tuple[str, int]], list[str]],
) -> Provider:
    provider_cls, links, queue, ignore = input
    provider = provider_cls()
    provider.message_queue = queue
    for url in links:
        provider.albums.extend(provider.fetch(url, ignore))
    queue.put(("Thumbnails", len(provider.albums)))
    # Only one at a time for better success rates, and this is usually not a bottleneck
    for album in provider.albums:
        if album.thumbnail is not None:
            album.thumbnail = load_thumbnail(album.thumbnail)
        queue.put("Thumbnails")
    return provider
