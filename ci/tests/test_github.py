"""Test shared GitHub API failure handling."""

import os
from unittest import mock

import httpx
import pytest

from monori.ci.lib.github import (
    GitHub,
    GitHubAPIError,
    is_admin,
    rerun_latest_pull_request_workflow,
)
from monori.common import JsonValue

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


def test_rerun_paginates_and_matches_the_pull_request_association() -> None:
    """Find the newest matching PR run beyond the first workflow-runs page."""
    github = mock.Mock()

    def request(method: str, path: str, payload: JsonValue = None) -> JsonValue:
        if method == "POST":
            return None
        assert method == "GET"
        assert payload is None
        if path == "/pulls/343":
            return {"head": {"sha": "head-sha"}}
        if path.endswith("page=1"):
            return {"workflow_runs": [{"id": index} for index in range(100)]}
        if path.endswith("page=2"):
            return {
                "workflow_runs": [
                    {
                        "id": 999,
                        "created_at": "2026-01-01",
                        "pull_requests": [{"number": 343}],
                    }
                ]
            }
        return None

    github.request.side_effect = request

    rerun_latest_pull_request_workflow(github, 343)

    github.request.assert_any_call("POST", "/actions/runs/999/rerun-failed-jobs")
    assert any("page=2" in call.args[1] for call in github.request.call_args_list)


def test_rerun_falls_back_to_the_pull_request_head_sha() -> None:
    """Match runs whose API payload omits the pull_requests association."""
    github = mock.Mock()
    github.request.side_effect = [
        {"head": {"sha": "abc"}},
        {"workflow_runs": [{"id": 9, "head_sha": "abc"}]},
        None,
    ]

    rerun_latest_pull_request_workflow(github, 42)

    github.request.assert_called_with("POST", "/actions/runs/9/rerun-failed-jobs")


def test_rerun_fails_when_no_pull_request_run_exists() -> None:
    """Report a missing workflow run instead of silently skipping the rerun."""
    github = mock.Mock()
    github.request.side_effect = [
        {"head": {"sha": "abc"}},
        {"workflow_runs": []},
    ]

    with pytest.raises(RuntimeError, match=r"No pr-checks\.yaml run found for PR #42"):
        rerun_latest_pull_request_workflow(github, 42)
