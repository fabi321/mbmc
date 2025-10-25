import sys
from argparse import ArgumentParser
from queue import Queue

import dotenv

from musicbrainz_submit.addrelease import start_server, edit_release, add_release
from musicbrainz_submit.gui import CollectorApp
from musicbrainz_submit.match_releases import (
    get_providers,
    find_missing_releases,
    merge_with_musicbrainz,
    to_mb_release,
)
from musicbrainz_submit.progress import Progress
from musicbrainz_submit.providers.music_brainz_provider import MusicBrainzProvider
from musicbrainz_submit.providers.provider import Album


def main() -> int:
    parser = ArgumentParser(
        description="Submit MusiocBrainz releases from various providers by artist."
    )
    parser.add_argument("mbid", help="MusicBrainz Artist ID or URL", type=str)
    parser.add_argument(
        "--no-harmony", "-n", action="store_true", help="Disable Harmony integration"
    )
    parser.add_argument(
        "--banned-urls",
        "-b",
        action="append",
        help="Urls that are not to be used",
        default=[],
    )
    args = parser.parse_args()
    dotenv.load_dotenv()
    app = CollectorApp()

    start_server()

    MB_ID: str = args.mbid.split("/")[-1]

    queue: Queue[str | tuple[str, int] | None] = Queue()
    progress = Progress(queue)
    progress.start()

    providers = get_providers(MB_ID, queue, args.banned_urls)

    queue.put(None)
    queue.join()
    progress.join()

    missing = find_missing_releases(MB_ID, providers)

    print(f"Missing releases: {', '.join(missing.keys())}")

    while missing:
        album, ignored_providers = missing.popitem()
        gathered_responses: list[Album] = []
        for provider in providers:
            if provider in ignored_providers:
                continue
            if not gathered_responses and isinstance(provider, MusicBrainzProvider):
                # If everything has been ignored, don't show MB provider
                continue
            provider.query = album
            response = app.ask_question(provider)
            if response[1]:
                gathered_responses.append(response[1])
        if gathered_responses:
            ignored_providers.extend(album.provider for album in gathered_responses)
            for i, provider in enumerate(ignored_providers):
                if isinstance(provider, MusicBrainzProvider):
                    # Never ignore MusicBrainzProvider
                    ignored_providers.pop(i)
                    break
            if len(ignored_providers) != len(providers):
                # If not all missing providers are processed, re-add to missing
                missing[album] = ignored_providers
            if any(
                isinstance(album.provider, MusicBrainzProvider)
                for album in gathered_responses
            ):
                mb_id, current_actions = merge_with_musicbrainz(gathered_responses)
                edit_release(mb_id, current_actions, not args.no_harmony)
            else:
                results = to_mb_release(gathered_responses, app)
                if results:
                    add_release(results, not args.no_harmony)
                else:
                    for response in gathered_responses:
                        if not isinstance(response.provider, MusicBrainzProvider):
                            ignored_providers.remove(response.provider)
                    missing[album] = ignored_providers

    input("Press Enter to continue...")
    # when done with GUI:
    app.destroy()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
