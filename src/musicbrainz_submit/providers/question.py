from abc import ABC
from dataclasses import dataclass
from typing import Optional, List, TypeVar, Union, Callable

from musicbrainz_submit.gui import CollectorApp
from musicbrainz_submit.providers.provider import Provider, Album, Track


class Unfiltered(Provider, ABC):
    def filter(self) -> list[Album]:
        return self.fetch()

    @staticmethod
    def relevant(url: str) -> bool:
        return False

    def url_types(self, album: Album) -> List[str]:
        return []

    def artist_url_types(self) -> List[str]:
        return []


@dataclass
class Option:
    prompt: str
    snippet: Optional[str]

    def to_album(self, provider: Provider) -> Album:
        return Album(
            title=self.prompt,
            snippet=self.snippet or "",
            url="",
            thumbnail=None,
            provider=provider,
            artist="",
            release_date="",
            tracks=[],
        )


class Select(Unfiltered):
    def __init__(self, title: str, options: list[Option]):
        super().__init__(title, "")
        self.options = options

    def fetch(self) -> list[Album]:
        return [option.to_album(self) for option in self.options]


def ask_question(
    title: str, options: list[Option], app: CollectorApp
) -> Optional[Option]:
    select = Select(title, options)
    while True:
        response = app.ask_question(select)
        chosen_album = response[1]
        if chosen_album is not None:
            for option in options:
                if option.prompt == chosen_album.title:
                    return option
        else:
            return None


T = TypeVar("T")
V = TypeVar("V", bound=Union[Album, Track])
PREVIOUS_MAPPINGS: dict[tuple[str, ...], str] = {}


def pick_reduction_option(
    title: str,
    albums: list[V],
    reduction_function: Callable[[V], tuple[str, T]],
    app: CollectorApp,
) -> Optional[T]:
    mapping: dict[str, tuple[T, list[str]]] = {}
    for album in albums:
        prompt, value = reduction_function(album)
        if not prompt:
            continue
        mapping.setdefault(prompt, (value, []))[1].append(album.provider.name)
    if len(mapping) == 0:
        return None
    if len(mapping) == 1:
        # Only one option, return it
        return next(iter(mapping.values()))[0]
    if previous_selection := PREVIOUS_MAPPINGS.get(tuple(mapping.keys())):
        return mapping[previous_selection][0]

    options = [
        Option(
            prompt=f"{prompt} ({len(providers)})",
            snippet=", ".join(providers),
        )
        for prompt, (_, providers) in sorted(
            mapping.items(), key=lambda x: len(x[1][1]), reverse=True
        )
    ]
    selection = ask_question(title, options, app)
    if selection is None:
        return None
    selected = selection.prompt.rsplit(" (", 1)[0]
    PREVIOUS_MAPPINGS[tuple(mapping.keys())] = selected
    return mapping[selected][0]
