"""Small typed GitHub API client for workflow-side Python code."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, cast

import httpx
from fastapi import status

if TYPE_CHECKING:
    from ci.lib.json import JsonValue

REQUEST_TIMEOUT_SECONDS = 30
HTTP_NO_CONTENT = status.HTTP_204_NO_CONTENT
HTTP_FORBIDDEN = status.HTTP_403_FORBIDDEN
HTTP_NOT_FOUND = status.HTTP_404_NOT_FOUND
GITHUB_PAGE_SIZE = 100


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
        if response.status_code == HTTP_NO_CONTENT:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            message = f"GitHub API {method} {path} failed: HTTP {response.status_code}"
            raise RuntimeError(message) from error
        return cast("JsonValue", response.json())
