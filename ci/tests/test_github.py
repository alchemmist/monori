"""Test shared GitHub API failure handling."""

import os
from unittest import mock

import httpx
import pytest

from ci.lib.github import GitHub


def test_mutating_forbidden_response_fails_the_request() -> None:
    """Reject a forbidden GitHub write instead of reporting success."""
    response = mock.Mock(status_code=403)
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "forbidden",
        request=httpx.Request("POST", "https://api.github.com/repos/org/repo/issues/1/labels"),
        response=response,
    )
    with (
        mock.patch.dict(
            os.environ,
            {
                "GITHUB_API_URL": "https://api.github.com",
                "GITHUB_REPOSITORY": "org/repo",
                "GITHUB_TOKEN": "token",
            },
        ),
        mock.patch("ci.lib.github.httpx.request", return_value=response),
        pytest.raises(RuntimeError, match="HTTP 403"),
    ):
        GitHub().request("POST", "/issues/1/labels", {"labels": ["failed"]})
