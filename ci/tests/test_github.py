"""Test shared GitHub API failure handling."""

import os
from unittest import mock

import httpx
import pytest

from monori.ci.lib.github import GitHub, GitHubAPIError, is_admin

GITHUB_ENV = {
    "GITHUB_API_URL": "https://api.github.com",
    "GITHUB_REPOSITORY": "org/repo",
    "GITHUB_TOKEN": "token",
}


def test_mutating_forbidden_response_fails_the_request() -> None:
    """Reject a forbidden GitHub write instead of reporting success."""
    response = mock.Mock(status_code=403)
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "forbidden",
        request=httpx.Request("POST", "https://api.github.com/repos/org/repo/issues/1/labels"),
        response=response,
    )
    with (
        mock.patch.dict(os.environ, GITHUB_ENV),
        mock.patch("monori.ci.lib.github.httpx.request", return_value=response),
        pytest.raises(RuntimeError, match="HTTP 403"),
    ):
        GitHub().request("POST", "/issues/1/labels", {"labels": ["failed"]})


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_missing_read_and_delete_are_idempotent(method: str) -> None:
    """Return None for the two operations where GitHub 404 means absent state."""
    response = mock.Mock(status_code=404, is_error=True)
    with (
        mock.patch.dict(os.environ, GITHUB_ENV),
        mock.patch("monori.ci.lib.github.httpx.request", return_value=response),
    ):
        assert GitHub().request(method, "/labels/missing") is None


def test_forbidden_permission_lookup_means_not_admin() -> None:
    """Treat a forbidden collaborator lookup as a denied permission check."""
    github = mock.Mock()
    github.request.side_effect = GitHubAPIError("GET", "/collaborators/user/permission", 403)

    assert not is_admin(github, "user")
