"""Store and mutate the fake GitHub service state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from monori.common import JsonValue, array_value, object_value, optional_string

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass
class FakeGitHubState:
    """Hold observable GitHub repository state for integration scenarios."""

    repository: str = "alchemmist/monori"
    bot_login: str = "github-actions[bot]"
    pulls: dict[int, dict[str, JsonValue]] = field(default_factory=dict)
    comments: dict[int, dict[str, JsonValue]] = field(default_factory=dict)
    labels: set[str] = field(default_factory=set)
    issue_labels: dict[int, set[str]] = field(default_factory=dict)
    permissions: dict[str, str] = field(default_factory=dict)
    workflow_runs: list[dict[str, JsonValue]] = field(default_factory=list)
    workflow_jobs: dict[int, list[dict[str, JsonValue]]] = field(default_factory=dict)
    rerun_requests: list[int] = field(default_factory=list)
    pull_files: dict[int, list[dict[str, JsonValue]]] = field(default_factory=dict)
    comparisons: dict[str, dict[str, JsonValue]] = field(default_factory=dict)
    contents: dict[str, str] = field(default_factory=dict)
    failures: dict[tuple[str, str], int] = field(default_factory=dict)
    requests: list[dict[str, JsonValue]] = field(default_factory=list)
    next_comment_id: int = 1
    next_reaction_id: int = 1

    def reset(self, payload: Mapping[str, JsonValue]) -> None:
        """Replace all state from a JSON-compatible integration-test fixture."""
        self.repository = optional_string(payload.get("repository")) or "alchemmist/monori"
        self.bot_login = optional_string(payload.get("bot_login")) or "github-actions[bot]"
        self.pulls = self._objects_by_integer(payload.get("pulls"), "number", "pulls")
        self.comments = self._objects_by_integer(payload.get("comments"), "id", "comments")
        self.labels = {
            label
            for item in array_value(payload.get("labels", []), "labels")
            if isinstance((label := item), str)
        }
        self.issue_labels = self._issue_labels(payload.get("issue_labels"))
        self.permissions = self._permissions(payload.get("permissions"))
        self.workflow_runs = [
            object_value(item, "workflow run")
            for item in array_value(payload.get("workflow_runs", []), "workflow runs")
        ]
        self.workflow_jobs = self._workflow_jobs(payload.get("workflow_jobs"))
        self.pull_files = self._pull_files(payload.get("pull_files"))
        self.comparisons = {
            reference: object_value(comparison, "comparison")
            for reference, comparison in object_value(
                payload.get("comparisons", {}), "comparisons"
            ).items()
        }
        self.contents = {
            key: content
            for key, value in object_value(payload.get("contents", {}), "contents").items()
            if isinstance((content := value), str)
        }
        self.failures = self._failures(payload.get("failures"))
        self.requests = []
        self.rerun_requests = []
        self.next_comment_id = max(self.comments, default=0) + 1
        reaction_ids = [
            reaction.get("id")
            for comment in self.comments.values()
            for reaction in array_value(comment.get("reactions", []), "comment reactions")
            if isinstance(reaction, dict)
        ]
        self.next_reaction_id = (
            max(
                (identifier for identifier in reaction_ids if isinstance(identifier, int)),
                default=0,
            )
            + 1
        )

    def snapshot(self) -> dict[str, JsonValue]:
        """Return the complete observable state as JSON-compatible data."""
        return {
            "repository": self.repository,
            "bot_login": self.bot_login,
            "pulls": cast("JsonValue", list(self.pulls.values())),
            "comments": cast("JsonValue", list(self.comments.values())),
            "labels": cast("JsonValue", sorted(self.labels)),
            "issue_labels": {
                str(number): cast("JsonValue", sorted(labels))
                for number, labels in self.issue_labels.items()
            },
            "permissions": cast("JsonValue", dict(self.permissions)),
            "workflow_runs": cast("JsonValue", self.workflow_runs),
            "workflow_jobs": {
                str(run_id): cast("JsonValue", jobs) for run_id, jobs in self.workflow_jobs.items()
            },
            "rerun_requests": cast("JsonValue", list(self.rerun_requests)),
            "pull_files": {
                str(number): cast("JsonValue", files) for number, files in self.pull_files.items()
            },
            "comparisons": cast("JsonValue", self.comparisons),
            "contents": cast("JsonValue", self.contents),
            "requests": cast("JsonValue", self.requests),
        }

    def record_request(self, method: str, path: str) -> None:
        """Record one repository API request for observable budget assertions."""
        self.requests.append({"method": method, "path": path})

    def create_comment(self, number: int, body: str) -> dict[str, JsonValue]:
        """Create one bot-authored issue comment and return it."""
        comment: dict[str, JsonValue] = {
            "id": self.next_comment_id,
            "issue_number": number,
            "body": body,
            "user": {"login": self.bot_login},
            "reactions": [],
        }
        self.comments[self.next_comment_id] = comment
        self.next_comment_id += 1
        return comment

    def add_reaction(self, comment_id: int, content: str) -> dict[str, JsonValue]:
        """Add one bot-authored reaction to a comment and return it."""
        reaction: dict[str, JsonValue] = {
            "id": self.next_reaction_id,
            "content": content,
            "user": {"login": self.bot_login},
        }
        comment = self.comments[comment_id]
        reactions = array_value(comment.setdefault("reactions", []), "comment reactions")
        reactions.append(reaction)
        self.next_reaction_id += 1
        return reaction

    @staticmethod
    def _objects_by_integer(
        value: JsonValue, key: str, context: str
    ) -> dict[int, dict[str, JsonValue]]:
        """Index JSON objects by a required integer field."""
        result: dict[int, dict[str, JsonValue]] = {}
        for item in array_value(value or [], context):
            entry = object_value(item, context)
            identifier = entry.get(key)
            if not isinstance(identifier, int):
                message = f"Expected integer {key} in {context}"
                raise TypeError(message)
            result[identifier] = entry
        return result

    @staticmethod
    def _issue_labels(value: JsonValue) -> dict[int, set[str]]:
        """Decode issue labels keyed by pull-request number."""
        result: dict[int, set[str]] = {}
        for key, raw_labels in object_value(value or {}, "issue labels").items():
            result[int(key)] = {
                label
                for item in array_value(raw_labels, "issue labels")
                if isinstance((label := item), str)
            }
        return result

    @staticmethod
    def _permissions(value: JsonValue) -> dict[str, str]:
        """Decode collaborator permissions keyed by login."""
        return {
            login: permission
            for login, raw_permission in object_value(value or {}, "permissions").items()
            if isinstance((permission := raw_permission), str)
        }

    @staticmethod
    def _pull_files(value: JsonValue) -> dict[int, list[dict[str, JsonValue]]]:
        """Decode changed-file fixtures keyed by pull-request number."""
        return {
            int(number): [
                object_value(item, "pull request file")
                for item in array_value(files, "pull request files")
            ]
            for number, files in object_value(value or {}, "pull files").items()
        }

    @staticmethod
    def _workflow_jobs(value: JsonValue) -> dict[int, list[dict[str, JsonValue]]]:
        """Decode workflow jobs keyed by workflow run identifier."""
        return {
            int(run_id): [
                object_value(item, "workflow job") for item in array_value(jobs, "workflow jobs")
            ]
            for run_id, jobs in object_value(value or {}, "workflow jobs").items()
        }

    @staticmethod
    def _failures(value: JsonValue) -> dict[tuple[str, str], int]:
        """Decode configured HTTP failures keyed by method and request path."""
        result: dict[tuple[str, str], int] = {}
        for item in array_value(value or [], "failures"):
            failure = object_value(item, "failure")
            method = optional_string(failure.get("method"))
            path = optional_string(failure.get("path"))
            status = failure.get("status")
            if method is None or path is None or not isinstance(status, int):
                message = "Failure fixtures require method, path, and integer status"
                raise TypeError(message)
            result[(method.upper(), path)] = status
        return result
