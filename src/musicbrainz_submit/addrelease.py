import uuid
from html import escape
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from webbrowser import open

from musicbrainz_submit.constants import MUSICBRAINZ_PORT

_form_template = """<!doctype html>
<meta charset="UTF-8">
<html>
<head>
    <title>Submit</title>
</head>
<body>
    <form action=https://musicbrainz.org/{action} method="post">\n
        {form_data}
        <input type="submit" value="Do submit">
    </form>
    <script>document.forms[0].submit()</script>
</body>
"""

_form_input_template = '<input type="hidden" name="{name}" value="{value}" >'


ACTIONS: dict[str, tuple[str, list[tuple[str, str]]]] = {}


class RequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        form_data = ACTIONS.get(self.path.lstrip("/"), None)
        if not form_data:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        form_dict = {name: value for name, value in form_data[1]}
        form_html = _get_form(form_data[0], form_dict)

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(form_html.encode("utf-8"))


def start_server():
    server = ThreadingHTTPServer(("localhost", MUSICBRAINZ_PORT), RequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()


def resolve_urls(urls: list[tuple[str, str]], harmony: bool) -> list[tuple[str, str]]:
    resolved: list[tuple[str, str]] = []
    counter: int = 0
    for url, type_ in urls:
        resolved.append((f"urls.{counter}.url", url))
        resolved.append((f"urls.{counter}.link_type", type_))
        counter += 1
    if harmony:
        resolved.append(
            ("redirect_uri", "https://harmony.pulsewidth.org.uk/release/actions")
        )
    return resolved


def edit_release(mb_id: str, urls: list[tuple[str, str]], harmony: bool):
    ACTIONS[mb_id] = (f"release/{mb_id}/edit", resolve_urls(urls, harmony))
    open(f"http://localhost:{MUSICBRAINZ_PORT}/{mb_id}")


def edit_artist(mb_id: str, urls: list[tuple[str, str]], harmony: bool):
    ACTIONS[mb_id] = (f"artist/{mb_id}/edit", resolve_urls(urls, harmony))
    open(f"http://localhost:{MUSICBRAINZ_PORT}/{mb_id}")


def add_release(form_data: dict[str, str], harmony: bool):
    name: str = str(uuid.uuid4())
    if harmony:
        form_data["redirect_uri"] = "https://harmony.pulsewidth.org.uk/release/actions"
    ACTIONS[name] = ("release/add", list(form_data.items()))
    open(f"http://localhost:{MUSICBRAINZ_PORT}/{name}")


def _get_form(action: str, form_data: dict[str, str]) -> str:
    return _form_template.format(
        action=action,
        form_data=_format_form_data(form_data),
    )


def _format_form_data(data: dict[str, str]) -> str:
    return "".join(
        _form_input_template.format(name=escape(name), value=escape(value))
        for name, value in data.items()
    )
