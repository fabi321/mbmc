import sys
from argparse import ArgumentParser
from queue import Queue

import dotenv

from mbmc.addrelease import start_server, edit_release, add_release
from mbmc.gui import CollectorApp
from mbmc.match_releases import (
    get_providers,
    find_missing_releases,
    to_mb_release, merge_mb_release,
)
from mbmc.progress import Progress
from mbmc.providers.music_brainz_provider import MusicBrainzProvider
from mbmc.providers.provider import Album, AlbumStatus
from mbmc.util import BANNED_ALBUMS


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
    mb_provider = providers[-1]
    non_mb_providers = providers[:-1]

    relevant_banned = BANNED_ALBUMS.setdefault(MB_ID, [])
    for provider in providers:
        for album in provider.albums:
            if album.url in relevant_banned:
                album.status = album.status.BANNED

    queue.put(None)
    queue.join()
    progress.join()

    find_missing_releases(MB_ID, providers)

    while True:
        for provider in non_mb_providers:
            current = provider.get_todo_name()
            if current is not None:
                break
        else:
            break
        gathered_responses: list[Album] = []
        for provider in non_mb_providers:
            if provider.is_done(current):
                continue
            provider.query = current
            response = app.ask_question(provider)
            if response[0] == "banned":
                if response[1]:
                    relevant_banned.append(response[1].url)
                    response[1].status = AlbumStatus.BANNED
            elif response[1]:
                gathered_responses.append(response[1])
        if gathered_responses:
            mb_provider.query = current
            mb_response = app.ask_question(mb_provider)
            if mb_response[1]:
                gathered_responses.append(mb_response[1])
            if any(
                isinstance(album.provider, MusicBrainzProvider)
                for album in gathered_responses
            ):
                mb_id, current_actions = merge_mb_release(gathered_responses, app)
                edit_release(mb_id, current_actions, not args.no_harmony)
                for album in gathered_responses:
                    album.status = AlbumStatus.COMPLETED
            else:
                results = to_mb_release(gathered_responses, app)
                if results:
                    add_release(results, not args.no_harmony)
        else:
            for provider in non_mb_providers:
                provider.ignore_album(current)

    input("Press Enter to continue...")
    # when done with GUI:
    app.destroy()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
