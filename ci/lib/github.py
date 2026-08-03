"""Small typed GitHub API client for workflow-side Python code."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import cast

from ci.lib.json import JsonValue


class GitHub:
    def __init__(self) -> None:
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        data = None if payload is None else json.dumps(payload).encode()
        api_path = path if path == "/user" else f"/repos/{self.repository}{path}"
        request = urllib.request.Request(
            f"{self.base_url}{api_path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return (
                    None
                    if response.status == 204
                    else cast("JsonValue", json.loads(response.read()))
                )
        except urllib.error.HTTPError as error:
            if error.code == 403 and method in {"POST", "PATCH", "DELETE"}:
                return None
            raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {error.code}") from error
