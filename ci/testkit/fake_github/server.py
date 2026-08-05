"""Serve the stateful fake GitHub API over HTTP."""

from __future__ import annotations

import json
import os
import re
import signal
import threading
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, cast, override

from monori.ci.testkit.fake_github.state import FakeGitHubState
from monori.common import JsonValue, array_value, object_value, optional_string

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType

HOST = os.environ.get("FAKE_GITHUB_HOST", "127.0.0.1")
PORT = int(os.environ.get("FAKE_GITHUB_PORT", "8080"))
STATE = FakeGitHubState()
REPOSITORY_PATH = re.compile(r"^/repos/(?P<repository>[^/]+/[^/]+)(?P<path>/.*)$")


@dataclass(frozen=True)
class RouteRequest:
    """Bundle a matched route with its JSON payload and query parameters."""

    match: re.Match[str]
    payload: JsonValue
    query: dict[str, list[str]]


type RouteHandler = Callable[[RouteRequest], tuple[int, JsonValue]]


class FakeGitHubHandler(BaseHTTPRequestHandler):
    """Handle the GitHub REST subset exercised by Monori CI."""

    server_version = "MonoriFakeGitHub/1.0"

    def do_GET(self) -> None:
        """Handle a fake GitHub GET request."""
        self._dispatch("GET")

    def do_POST(self) -> None:
        """Handle a fake GitHub POST request."""
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        """Handle a fake GitHub PATCH request."""
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        """Handle a fake GitHub DELETE request."""
        self._dispatch("DELETE")

    @override
    def log_message(self, format_string: str, *args: str | float | None) -> None:
        """Suppress access logs so test output contains only scenario failures."""
        if format_string or args:
            return

    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        payload = self._read_payload()
        failure = STATE.failures.get((method, parsed.path))
        if failure is not None:
            response: tuple[int, JsonValue] | None = (
                failure,
                {"message": "configured failure"},
            )
        else:
            response = self._special_response(method, parsed.path, payload)
            if response is None:
                response = self._repository_response(
                    method,
                    parsed.path,
                    payload,
                    urllib.parse.parse_qs(parsed.query),
                )
        status, body = response or (HTTPStatus.NOT_FOUND, {"message": "not found"})
        self._respond(status, body)

    @staticmethod
    def _special_response(
        method: str, path: str, payload: JsonValue
    ) -> tuple[int, JsonValue] | None:
        """Handle service-control routes outside a repository namespace."""
        if path == "/health" and method == "GET":
            return HTTPStatus.OK, {"status": "ok"}
        if path == "/_test/reset" and method == "POST":
            STATE.reset(object_value(payload, "reset payload"))
            return HTTPStatus.NO_CONTENT, None
        if path == "/_test/state" and method == "GET":
            return HTTPStatus.OK, STATE.snapshot()
        if path == "/user" and method == "GET":
            return HTTPStatus.OK, {"login": STATE.bot_login}
        return None

    def _repository_response(
        self,
        method: str,
        path: str,
        payload: JsonValue,
        query: dict[str, list[str]],
    ) -> tuple[int, JsonValue] | None:
        """Route one request within the configured fake repository."""
        repository_match = REPOSITORY_PATH.fullmatch(path)
        if repository_match is None or repository_match.group("repository") != STATE.repository:
            return None
        route = repository_match.group("path")
        routes: tuple[tuple[str, re.Pattern[str], RouteHandler], ...] = (
            ("GET", re.compile(r"^/pulls/(?P<number>\d+)$"), self._get_pull),
            ("PATCH", re.compile(r"^/pulls/(?P<number>\d+)$"), self._patch_pull),
            ("GET", re.compile(r"^/pulls/(?P<number>\d+)/files$"), self._pull_files),
            ("GET", re.compile(r"^/compare/(?P<reference>.+)$"), self._comparison),
            ("GET", re.compile(r"^/issues/(?P<number>\d+)/comments$"), self._issue_comments),
            ("POST", re.compile(r"^/issues/(?P<number>\d+)/comments$"), self._create_comment),
            ("GET", re.compile(r"^/issues/comments/(?P<identifier>\d+)$"), self._get_comment),
            ("PATCH", re.compile(r"^/issues/comments/(?P<identifier>\d+)$"), self._patch_comment),
            (
                "GET",
                re.compile(r"^/issues/comments/(?P<identifier>\d+)/reactions$"),
                self._get_reactions,
            ),
            (
                "POST",
                re.compile(r"^/issues/comments/(?P<identifier>\d+)/reactions$"),
                self._create_reaction,
            ),
            (
                "DELETE",
                re.compile(r"^/issues/comments/(?P<identifier>\d+)/reactions/(?P<reaction>\d+)$"),
                self._delete_reaction,
            ),
            ("GET", re.compile(r"^/labels/(?P<name>.+)$"), self._get_label),
            ("POST", re.compile(r"^/labels$"), self._create_label),
            ("GET", re.compile(r"^/issues/(?P<number>\d+)/labels$"), self._get_labels),
            ("POST", re.compile(r"^/issues/(?P<number>\d+)/labels$"), self._add_labels),
            (
                "DELETE",
                re.compile(r"^/issues/(?P<number>\d+)/labels/(?P<name>.+)$"),
                self._delete_label,
            ),
            (
                "GET",
                re.compile(r"^/collaborators/(?P<login>[^/]+)/permission$"),
                self._permission,
            ),
            ("GET", re.compile(r"^/actions/workflows/[^/]+/runs$"), self._workflow_runs),
            (
                "POST",
                re.compile(r"^/actions/runs/(?P<identifier>\d+)/rerun-failed-jobs$"),
                self._rerun,
            ),
        )
        for expected_method, pattern, handler in routes:
            if method == expected_method and (match := pattern.fullmatch(route)) is not None:
                return handler(RouteRequest(match, payload, query))
        return None

    def _get_pull(self, request: RouteRequest) -> tuple[int, JsonValue]:
        pull = STATE.pulls.get(int(request.match.group("number")))
        return (HTTPStatus.OK, pull) if pull is not None else (HTTPStatus.NOT_FOUND, None)

    def _patch_pull(self, request: RouteRequest) -> tuple[int, JsonValue]:
        number = int(request.match.group("number"))
        pull = STATE.pulls.get(number)
        if pull is None:
            return HTTPStatus.NOT_FOUND, None
        pull.update(object_value(request.payload, "pull request update"))
        return HTTPStatus.OK, pull

    def _pull_files(self, request: RouteRequest) -> tuple[int, JsonValue]:
        files = STATE.pull_files.get(int(request.match.group("number")), [])
        return HTTPStatus.OK, cast("JsonValue", files)

    def _comparison(self, request: RouteRequest) -> tuple[int, JsonValue]:
        reference = urllib.parse.unquote(request.match.group("reference"))
        comparison = STATE.comparisons.get(reference)
        return (
            (HTTPStatus.OK, comparison) if comparison is not None else (HTTPStatus.NOT_FOUND, None)
        )

    def _issue_comments(self, request: RouteRequest) -> tuple[int, JsonValue]:
        number = int(request.match.group("number"))
        comments = [
            comment for comment in STATE.comments.values() if comment.get("issue_number") == number
        ]
        return HTTPStatus.OK, cast("JsonValue", comments)

    def _create_comment(self, request: RouteRequest) -> tuple[int, JsonValue]:
        body = optional_string(object_value(request.payload, "comment").get("body")) or ""
        number = int(request.match.group("number"))
        return HTTPStatus.CREATED, STATE.create_comment(number, body)

    def _get_comment(self, request: RouteRequest) -> tuple[int, JsonValue]:
        comment = STATE.comments.get(int(request.match.group("identifier")))
        return (HTTPStatus.OK, comment) if comment is not None else (HTTPStatus.NOT_FOUND, None)

    def _patch_comment(self, request: RouteRequest) -> tuple[int, JsonValue]:
        comment = STATE.comments.get(int(request.match.group("identifier")))
        if comment is None:
            return HTTPStatus.NOT_FOUND, None
        comment.update(object_value(request.payload, "comment update"))
        return HTTPStatus.OK, comment

    def _get_reactions(self, request: RouteRequest) -> tuple[int, JsonValue]:
        comment = STATE.comments.get(int(request.match.group("identifier")))
        if comment is None:
            return HTTPStatus.NOT_FOUND, None
        return HTTPStatus.OK, comment.get("reactions", [])

    def _create_reaction(self, request: RouteRequest) -> tuple[int, JsonValue]:
        identifier = int(request.match.group("identifier"))
        if identifier not in STATE.comments:
            return HTTPStatus.NOT_FOUND, None
        content = optional_string(object_value(request.payload, "reaction").get("content")) or ""
        return HTTPStatus.CREATED, STATE.add_reaction(identifier, content)

    def _delete_reaction(self, request: RouteRequest) -> tuple[int, JsonValue]:
        comment = STATE.comments.get(int(request.match.group("identifier")))
        if comment is None:
            return HTTPStatus.NOT_FOUND, None
        reaction_id = int(request.match.group("reaction"))
        reactions = array_value(comment.get("reactions", []), "comment reactions")
        comment["reactions"] = [
            reaction
            for reaction in reactions
            if not isinstance(reaction, dict) or reaction.get("id") != reaction_id
        ]
        return HTTPStatus.NO_CONTENT, None

    def _get_label(self, request: RouteRequest) -> tuple[int, JsonValue]:
        name = urllib.parse.unquote(request.match.group("name"))
        return (
            (HTTPStatus.OK, {"name": name})
            if name in STATE.labels
            else (HTTPStatus.NOT_FOUND, None)
        )

    def _create_label(self, request: RouteRequest) -> tuple[int, JsonValue]:
        name = optional_string(object_value(request.payload, "label").get("name")) or ""
        STATE.labels.add(name)
        return HTTPStatus.CREATED, {"name": name}

    def _get_labels(self, request: RouteRequest) -> tuple[int, JsonValue]:
        labels = sorted(STATE.issue_labels.get(int(request.match.group("number")), set()))
        return HTTPStatus.OK, cast("JsonValue", [{"name": name} for name in labels])

    def _add_labels(self, request: RouteRequest) -> tuple[int, JsonValue]:
        number = int(request.match.group("number"))
        raw_labels = object_value(request.payload, "labels").get("labels")
        names = {
            name for item in array_value(raw_labels, "labels") if isinstance((name := item), str)
        }
        STATE.labels.update(names)
        STATE.issue_labels.setdefault(number, set()).update(names)
        return HTTPStatus.OK, cast("JsonValue", [{"name": name} for name in sorted(names)])

    def _delete_label(self, request: RouteRequest) -> tuple[int, JsonValue]:
        number = int(request.match.group("number"))
        name = urllib.parse.unquote(request.match.group("name"))
        STATE.issue_labels.setdefault(number, set()).discard(name)
        return HTTPStatus.NO_CONTENT, None

    def _permission(self, request: RouteRequest) -> tuple[int, JsonValue]:
        login = urllib.parse.unquote(request.match.group("login"))
        permission = STATE.permissions.get(login)
        return (
            (HTTPStatus.OK, {"permission": permission})
            if permission is not None
            else (HTTPStatus.NOT_FOUND, None)
        )

    def _workflow_runs(self, request: RouteRequest) -> tuple[int, JsonValue]:
        page = int(request.query.get("page", ["1"])[0])
        per_page = int(request.query.get("per_page", ["100"])[0])
        start = (page - 1) * per_page
        runs = STATE.workflow_runs[start : start + per_page]
        return HTTPStatus.OK, {"workflow_runs": cast("JsonValue", runs)}

    def _rerun(self, request: RouteRequest) -> tuple[int, JsonValue]:
        STATE.rerun_requests.append(int(request.match.group("identifier")))
        return HTTPStatus.CREATED, {}

    def _read_payload(self) -> JsonValue:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return None
        return cast("JsonValue", json.loads(self.rfile.read(length)))

    def _respond(self, status: int, body: JsonValue = None) -> None:
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        if data:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)


def main() -> None:
    """Run the fake GitHub service until its process is terminated."""
    server = ThreadingHTTPServer((HOST, PORT), FakeGitHubHandler)

    def stop_server(signum: int, frame: FrameType | None) -> None:
        """Stop the HTTP loop from outside its signal-handler thread."""
        if signum in {signal.SIGINT, signal.SIGTERM}:
            name = frame.f_code.co_name if frame is not None else "fake-github-shutdown"
            threading.Thread(target=server.shutdown, name=name, daemon=True).start()

    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
