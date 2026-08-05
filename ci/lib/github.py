"""Small typed GitHub API client for workflow-side Python code."""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
from http import HTTPStatus
from typing import TYPE_CHECKING, Protocol, cast

import httpx

from monori.common import array_value, object_value, optional_string

if TYPE_CHECKING:
    from monori.common import JsonValue

REQUEST_TIMEOUT_SECONDS = 30
GITHUB_PAGE_SIZE = 100


class GitHubAPI(Protocol):
    """Describe the GitHub transport required by reusable CI primitives."""

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Execute one GitHub API request and return its decoded response."""
        ...


class RepositoryGitHubAPI(GitHubAPI, Protocol):
    """Describe the complete repository API used by source checks."""

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        """Read all pages from a list endpoint."""
        ...

    def file_text(self, path: str, ref: str) -> str | None:
        """Load repository file contents at a Git reference."""
        ...


class GitHubAPIError(RuntimeError):
    """Represent an unexpected GitHub HTTP response."""

    def __init__(self, method: str, path: str, status_code: int) -> None:
        """Initialize the error with request context."""
        message = f"GitHub API {method} {path} failed: HTTP {status_code}"
        super().__init__(message)
        self.status_code = status_code


class GitHub:
    """Typed GitHub API client for workflow scripts."""

    def __init__(self) -> None:
        """Initialize API client defaults from environment."""
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Send GitHub API request and return parsed JSON response."""
        data = None if payload is None else json.dumps(payload).encode()
        api_path = path if path == "/user" else f"/repos/{self.repository}{path}"
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{api_path}",
                content=data,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Content-Type": "application/json",
                },
            )
        except httpx.RequestError as error:
            message = f"GitHub API {method} {path} failed: {error}"
            raise RuntimeError(message) from error
        if response.status_code == HTTPStatus.NO_CONTENT:
            return None
        if response.status_code == HTTPStatus.NOT_FOUND and method in {"GET", "DELETE"}:
            return None
        if response.is_error:
            raise GitHubAPIError(method, path, response.status_code)
        return cast("JsonValue", response.json())

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        """Read every page from a GitHub list endpoint."""
        result: list[dict[str, JsonValue]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            page_path = f"{path}{separator}per_page={GITHUB_PAGE_SIZE}&page={page}"
            items = array_value(self.request("GET", page_path), page_path)
            result.extend(object_value(item, page_path) for item in items)
            if len(items) < GITHUB_PAGE_SIZE:
                return result
            page += 1

    def file_text(self, path: str, ref: str) -> str | None:
        """Read repository file contents at a Git reference."""
        encoded_path = urllib.parse.quote(path, safe="")
        encoded_ref = urllib.parse.quote(ref, safe="")
        response = self.request("GET", f"/contents/{encoded_path}?ref={encoded_ref}")
        if response is None:
            return None
        data = object_value(response, path)
        content = optional_string(data.get("content"))
        if content:
            return base64.b64decode(content).decode()
        download_url = optional_string(data.get("download_url"))
        if download_url is None:
            return None
        try:
            downloaded = httpx.get(
                download_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            downloaded.raise_for_status()
        except httpx.HTTPError as error:
            message = f"Cannot read {path} at {ref}: {error}"
            raise RuntimeError(message) from error
        return downloaded.text

    def ensure_label(self, name: str) -> None:
        """Create a repository label when it does not exist."""
        ensure_label(self, name)

    def is_admin(self, login: str) -> bool:
        """Return whether a repository collaborator has admin permission."""
        return is_admin(self, login)

    def sync_label(self, number: int, name: str, *, present: bool) -> None:
        """Set or remove a pull-request label."""
        sync_label(self, number, name, present=present)


def ensure_label(github: GitHubAPI, name: str) -> None:
    """Create a repository label when it does not exist."""
    encoded = urllib.parse.quote(name, safe="")
    if github.request("GET", f"/labels/{encoded}") is None:
        github.request("POST", "/labels", {"name": name, "color": "b60205"})


def is_admin(github: GitHubAPI, login: str) -> bool:
    """Return whether a repository collaborator has admin permission."""
    encoded = urllib.parse.quote(login, safe="")
    try:
        response = github.request("GET", f"/collaborators/{encoded}/permission")
    except GitHubAPIError as error:
        if error.status_code == HTTPStatus.FORBIDDEN:
            return False
        raise
    return (
        response is not None and object_value(response, "permission").get("permission") == "admin"
    )


def sync_label(github: GitHubAPI, number: int, name: str, *, present: bool) -> None:
    """Set or remove a pull-request label."""
    encoded = urllib.parse.quote(name, safe="")
    if present:
        ensure_label(github, name)
        github.request("POST", f"/issues/{number}/labels", {"labels": [name]})
    else:
        github.request("DELETE", f"/issues/{number}/labels/{encoded}")
