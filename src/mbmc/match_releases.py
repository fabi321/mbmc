import re
from multiprocessing.pool import ThreadPool
from queue import Queue
from typing import Optional

from mbmc.gui import CollectorApp
from mbmc.music_brainz import (
    get_artist,
    get_releases,
    find_url,
    normalize_url,
)
from mbmc.prefetch import prefetch_provider
from mbmc.providers.apple_music import AppleMusicProvider
from mbmc.providers.bandcamp import BandcampProvider
from mbmc.providers.deezer import DeezerProvider
from mbmc.providers.discogs import DiscogsProvider
from mbmc.providers.music_brainz_provider import MusicBrainzProvider
from mbmc.providers.provider import Provider, Album, ArtistFormat, Track, AlbumStatus
from mbmc.providers.question import (
    pick_reduction_option,
    ask_question,
    Option,
    PREVIOUS_MAPPINGS,
)
from mbmc.providers.spotify import SpotifyProvider
from mbmc.providers.tidal import TidalProvider
from mbmc.providers.vk_music import VkMusicProvider
from mbmc.providers.youtube_music import YouTubeMusicProvider

PROVIDERS = [
    BandcampProvider,
    SpotifyProvider,
    DeezerProvider,
    TidalProvider,
    AppleMusicProvider,
    YouTubeMusicProvider,
    # MetalArchivesProvider, !! broken tue to cf
    VkMusicProvider,
    DiscogsProvider,
    MusicBrainzProvider,
]


def get_providers(
    mb_id: str, queue: Queue[str | tuple[str, int]], banned_urls: list[str]
) -> list[Provider]:
    artist = get_artist(mb_id)
    relevant_urls: list[str] = []
    for url in artist.get("url-relation-list", []):
        if url["target"] not in banned_urls:
            relevant_urls.append(url["target"])
    relevant_urls.append(f"https://musicbrainz.org/artist/{mb_id}")
    pairings: dict[type[Provider], set[str]] = {cls: set() for cls in PROVIDERS}

    for link in relevant_urls:
        for provider_cls, relevant in pairings.items():
            if provider_cls.relevant(link):
                relevant.update(link)

    with ThreadPool(15) as pool:
        providers = pool.map(prefetch_provider, (
            (provider_cls, links, queue)
            for provider_cls, links in pairings.items()
            if links
        ))
    return providers


def normalize_name(name: str) -> str:
    return name.lower().strip()


def find_missing_releases(mb_id: str, providers: list[Provider]):
    to_find: dict[str, Album] = {}
    for provider in providers:
        if isinstance(provider, MusicBrainzProvider):
            continue
        for album in provider.albums:
            to_find[album.url] = album

    releases = get_releases(mb_id)
    for album in releases:
        for url in album.get("url-relation-list", []):
            if found := to_find.get(normalize_url(url["target"]), None):
                found.status = AlbumStatus.COMPLETED


def album_to_track_layout(album: Album) -> tuple[str, list[tuple[int, int]]]:
    tracks = [(track.disk_nr, track.track_nr) for track in album.tracks]
    # combine disk layout into single string for easy comparison
    # e.g. "Disk 1: 1-5, Disk 2: 1-4"
    layout = []
    current_disk = None
    current_range_start = None
    current_range_end = None

    def push_range(disk_nr: Optional[int] = None, track_nr: Optional[int] = None):
        nonlocal current_range_start, current_range_end, current_disk
        if current_range_start is not None:
            if current_range_start == current_range_end:
                layout.append(f"{current_range_start}, ")
            else:
                layout.append(f"{current_range_start}-{current_range_end}, ")
        current_disk = disk_nr
        current_range_start = track_nr
        current_range_end = track_nr

    for disk_nr, track_nr in tracks:
        if disk_nr != current_disk:
            push_range(disk_nr, track_nr)
            layout.append(f"Disk {disk_nr}: ")
        else:
            if track_nr == current_range_end + 1:
                current_range_end = track_nr
            else:
                push_range(disk_nr, track_nr)
    push_range()
    layout_str = "".join(layout).removesuffix(", ")
    return layout_str, tracks


def album_to_track_length(album: Album) -> tuple[str, list[int]]:
    lengths = [track.duration for track in album.tracks]

    def format_length(ms: int) -> str:
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        tmp: str = f"{minutes}:{seconds:02d}"
        if ms % 1000 != 0:
            tmp += f".{ms % 1000:03d}"
        return tmp

    length_str = ", ".join(format_length(length) for length in lengths)
    return length_str, lengths


def album_to_title(album: Album) -> tuple[str, str]:
    return album.title, album.title


def album_to_track_title(album: Album) -> tuple[str, list[str]]:
    titles = [track.title for track in album.tracks]
    title_str = ", ".join(titles)
    return title_str, titles


def inner_extract_featured(
    artist: ArtistFormat, name: str
) -> tuple[list[str | tuple[str, str]], str]:
    extracted: list[str | tuple[str, str]]
    if isinstance(artist, str):
        extracted = [artist]
    else:
        extracted = artist
    if "feat." in name.lower() or "ft." in name.lower():
        main_artist, featured_part = re.split(r"f(?:ea)?t\.", name, flags=re.IGNORECASE)
        if main_artist.endswith("("):
            main_artist = main_artist[:-1].strip()
            featured_part = featured_part.replace(")", "", 1).strip()
        if "(" in featured_part and ")" in featured_part:
            featured_part, addition = featured_part.split("(", 1)
            main_artist += "(" + addition
        featured_names = [n.strip() for n in featured_part.replace("&", ",").split(",")]
        for feat_name in featured_names:
            for entry in extracted:
                entry_name = entry[0] if isinstance(entry, tuple) else entry
                if normalize_name(entry_name) == normalize_name(feat_name):
                    break
            else:
                if " feat. " in extracted:
                    extracted.append(", ")
                else:
                    extracted.append(" feat. ")
                extracted.append((feat_name, "unknown"))
        return extracted, main_artist.strip()
    return extracted, name


def extract_featured(album: Album):
    album.artist, album.title = inner_extract_featured(album.artist, album.title)
    for track in album.tracks:
        track.artist, track.title = inner_extract_featured(track.artist, track.title)


def album_to_album_artist(
    album: Album | Track,
) -> tuple[str, list[str | tuple[str, str]]]:
    artist = album.artist
    artist_list: list[str | tuple[str, Optional[str]]]
    assert not isinstance(artist, str)
    artist_list = []
    # Automatically add ", " between artist entries, if the source didn't provide it
    has_join_phrase: bool = True
    for entry in artist:
        if isinstance(entry, str):
            if has_join_phrase:
                artist_list.append((entry, None))
            else:
                artist_list.append(entry)
            has_join_phrase = not has_join_phrase
        else:
            if not has_join_phrase:
                artist_list.append(", ")
            artist_list.append((entry[0], find_url(entry[1])))
            has_join_phrase = False
    artist_str = "".join(
        (
            (f"[{artist[0]}]" if artist[1] else f"{{{artist[0]}}}")
            if isinstance(artist, tuple)
            else artist
        )
        for artist in artist_list
    )
    return artist_str, artist_list


def album_to_release_date(album: Album) -> tuple[str, str]:
    return album.release_date, album.release_date


def album_to_barcode(album: Album) -> tuple[str, str]:
    barcode = str(album.upn or "")
    return barcode, barcode


def artist_credit_to_mb_format(artist: ArtistFormat, prefix: str) -> dict[str, str]:
    assert not isinstance(artist, str)
    result = {}
    counter = 0
    for entry in artist:
        start: str = f"{prefix}.names.{counter}"
        if isinstance(entry, str):
            result[f"{start}.join_phrase"] = entry
            counter += 1
        else:
            result[f"{start}.name"] = entry[0]
            result[f"{start}.artist.name"] = entry[0]
            if entry[1]:
                result[f"{start}.mbid"] = entry[1]
    return result


def select_release_type(app: CollectorApp) -> Optional[str]:
    options = [
        "Album",
        "Single",
        "EP",
        "Other",
    ]
    option_objs = [Option(prompt=option, snippet="") for option in options]
    selected = ask_question("Select release type", option_objs, app)
    if selected is None:
        return None
    return selected.prompt


RELEASE_LANGUAGE_SCRIPTS: dict[str, tuple[str, str]] = {
    "English": ("eng", "Latn"),
    "German": ("deu", "Latn"),
    "French": ("fra", "Latn"),
    "Spanish": ("spa", "Latn"),
    "Italian": ("ita", "Latn"),
    "Japanese": ("jpn", "Jpan"),
    "Russian": ("rus", "Cyrl"),
    "Ukrainian": ("ukr", "Cyrl"),
    "Unknown": ("und", "Zyyy"),
}


def select_release_language(app: CollectorApp) -> Optional[str]:
    option_objs = [
        Option(prompt=option, snippet="") for option in RELEASE_LANGUAGE_SCRIPTS
    ]
    selected = ask_question("Select release language", option_objs, app)
    if selected is None:
        return None
    return selected.prompt


def to_mb_release(albums: list[Album], app: CollectorApp) -> Optional[dict[str, str]]:
    PREVIOUS_MAPPINGS.clear()
    name: str = pick_reduction_option("Select album title", albums, album_to_title, app)
    if name is None:
        return None
    track_layout = pick_reduction_option(
        "Select track layout", albums, album_to_track_layout, app
    )
    if track_layout is None:
        return None
    # Remove albums that don't match the chosen track layout
    for i in range(len(albums) - 1, -1, -1):
        if not albums[i].tracks:
            continue
        if len(albums[i].tracks) != len(track_layout):
            albums.pop(i)
    track_lengths = pick_reduction_option(
        "Select track lengths", albums, album_to_track_length, app
    )
    if track_lengths is None:
        return None
    for album in albums:
        extract_featured(album)
    track_titles = pick_reduction_option(
        "Select track titles", albums, album_to_track_title, app
    )
    if track_titles is None:
        return None
    album_artist = pick_reduction_option(
        "Select album artist", albums, album_to_album_artist, app
    )
    if album_artist is None:
        return None
    release_date = pick_reduction_option(
        "Select release date", albums, album_to_release_date, app
    )
    if release_date is None:
        return None
    barcode = pick_reduction_option("Select barcode", albums, album_to_barcode, app)
    release_type = select_release_type(app)
    if release_type is None:
        return None
    release_language = select_release_language(app)
    if release_language is None:
        return None
    result: dict[str, str] = {"name": name}
    for i in range(len(track_titles)):
        disk_id, track_id = track_layout[i]
        if track_id == 1:
            result[f"mediums.{disk_id - 1}.format"] = "Digital Media"
        mb_name: str = f"mediums.{disk_id - 1}.track.{track_id - 1}"
        name = track_titles[i]
        artist = pick_reduction_option(
            f"Select artist for track {name}",
            [album.tracks[i] for album in albums if album.tracks],
            album_to_album_artist,
            app,
        )
        result[f"{mb_name}.name"] = name
        result[f"{mb_name}.number"] = str(track_id)
        result[f"{mb_name}.length"] = str(track_lengths[i])
        result.update(artist_credit_to_mb_format(artist, f"{mb_name}.artist_credit"))
    counter = 0
    for album in albums:
        for url_type in album.provider.url_types(album):
            result[f"urls.{counter}.url"] = album.url
            result[f"urls.{counter}.link_type"] = url_type
            counter += 1
    if barcode:
        result["barcode"] = barcode
    result["type"] = release_type
    if release_language != "Unknown":
        lang, script = RELEASE_LANGUAGE_SCRIPTS[release_language]
        result["language"] = lang
        result["script"] = script
    result.update(artist_credit_to_mb_format(album_artist, "artist_credit"))
    if release_date.count("-") == 0:
        result["events.0.date.year"] = release_date
    elif release_date.count("-") == 2:
        year, month, day = release_date.split("-")
        result["events.0.date.year"] = year
        result["events.0.date.month"] = month
        result["events.0.date.day"] = day
    result["events.0.country"] = "XW"
    edit_note: str = ""
    for album in albums:
        edit_note += f"Sourced from {album.url}\n"
    edit_note += "\n Added via mbmc: https://github.com/fabi321/mbmc"
    result["edit_note"] = edit_note
    result["status"] = "official"
    for album in albums:
        album.status = AlbumStatus.COMPLETED
    return result


def merge_mb_release(albums: list[Album], app: CollectorApp) -> Optional[tuple[str, dict[str, str]]]:
    non_mb = []
    mb_release = None
    for album in albums:
        if isinstance(album.provider, MusicBrainzProvider):
            mb_release = album
        else:
            non_mb.append(album)
    assert mb_release is not None
    assert non_mb
    PREVIOUS_MAPPINGS.clear()
    track_layout = pick_reduction_option(
        "Select track layout", albums, album_to_track_layout, app
    )
    if track_layout is None:
        return None
    # Remove albums that don't match the chosen track layout
    for i in range(len(albums) - 1, -1, -1):
        if not albums[i].tracks:
            continue
        if len(albums[i].tracks) != len(track_layout):
            removed = albums.pop(i)
            if removed == mb_release:
                return None
    release_date = pick_reduction_option(
        "Select release date", albums, album_to_release_date, app
    )
    if release_date is None:
        return None
    barcode = pick_reduction_option("Select barcode", albums, album_to_barcode, app)
    result: dict[str, str] = {}
    counter = 0
    for album in albums:
        for url_type in album.provider.url_types(album):
            result[f"urls.{counter}.url"] = album.url
            result[f"urls.{counter}.link_type"] = url_type
            counter += 1
    if barcode:
        result["barcode"] = barcode
    if release_date.count("-") == 0:
        result["events.0.date.year"] = release_date
    elif release_date.count("-") == 2:
        year, month, day = release_date.split("-")
        result["events.0.date.year"] = year
        result["events.0.date.month"] = month
        result["events.0.date.day"] = day
    result["events.0.country"] = mb_release.extra_data["release_country"] or "XW"
    edit_note: str = ""
    for album in albums:
        edit_note += f"Sourced from {album.url}\n"
    edit_note += "\n Matched via mbmc: https://github.com/fabi321/mbmc"
    result["edit_note"] = edit_note
    for album in albums:
        if not isinstance(album.provider, MusicBrainzProvider):
            album.status = AlbumStatus.COMPLETED
    return mb_release.extra_data["mbid"], result
