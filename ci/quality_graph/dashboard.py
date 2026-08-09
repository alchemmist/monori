"""Render and publish the single pull-request Quality Graph dashboard."""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from monori.ci.lib.comments import (
    delete_managed_comments,
    managed_comment,
    upsert_comment,
)
from monori.ci.lib.github import GITHUB_PAGE_SIZE, GitHub, GitHubAPI
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobResult,
    JobStatus,
    controls_from_markdown,
    read_job_result,
)
from monori.ci.quality_graph.registry import registered_checks, workflow_jobs
from monori.common import JsonValue, array_value, object_value, optional_string, string_value

if TYPE_CHECKING:
    from collections.abc import Iterable

DASHBOARD_MARKER = "quality-graph"
LEGACY_REPORT_MARKERS = {
    "bundle-size",
    "frontend-performance",
    "mutation",
    "object-annotations",
    "suppression",
}
TEMPLATE_ENVIRONMENT = Environment(
    loader=FileSystemLoader(Path(__file__).with_name("templates")),
    undefined=StrictUndefined,
    autoescape=select_autoescape(default=False),
    keep_trailing_newline=True,
)
DASHBOARD_TEMPLATE = TEMPLATE_ENVIRONMENT.get_template("dashboard.md.j2")
MANAGED_MARKER_RE = re.compile(r"\A<!-- monori-report: quality-graph -->\s*")
NOTICE_RE = re.compile(
    r"<!-- monori-qg-notice:start -->.*?<!-- monori-qg-notice:end -->",
    re.DOTALL,
)
DEFAULT_WATCH_INTERVAL = 5.0
DEFAULT_WATCH_TIMEOUT = 2700.0


@dataclass(frozen=True)
class DashboardJob:
    """Represent one compact workflow status row."""

    job_id: str
    title: str
    status: JobStatus
    summary_url: str
    logs_url: str
    metric: str = "—"


@dataclass(frozen=True)
class DashboardControlGroup:
    """Group administrator controls belonging to one check."""

    job_id: str
    title: str
    controls: tuple[JobControl, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DashboardModel:
    """Provide all typed data consumed by the dashboard template."""

    status: JobStatus
    message: str
    run_id: int
    run_attempt: int
    head_sha: str
    jobs: tuple[DashboardJob, ...]
    control_groups: tuple[DashboardControlGroup, ...] = ()


def render_dashboard(model: DashboardModel) -> str:
    """Render the compact pull-request dashboard."""
    return re.sub(r"\n{3,}", "\n\n", DASHBOARD_TEMPLATE.render(model=model).strip()) + "\n"


def load_results(directory: Path) -> dict[str, JobResult]:
    """Load every result artifact downloaded for the current workflow run."""
    results: dict[str, JobResult] = {}
    if not directory.exists():
        return results
    for path in sorted(directory.rglob("*.json")):
        result = read_job_result(path)
        results[result.check_id] = result
    return results


def dashboard_status(jobs: Iterable[DashboardJob]) -> JobStatus:
    """Derive the dashboard verdict from all displayed jobs."""
    return aggregate_status(job.status for job in jobs)


def aggregate_status(statuses: Iterable[JobStatus]) -> JobStatus:
    """Derive the dashboard verdict from job statuses."""
    observed = set(statuses)
    if JobStatus.IN_PROGRESS in observed or JobStatus.WAITING in observed:
        return JobStatus.IN_PROGRESS
    if JobStatus.FAILED in observed:
        return JobStatus.FAILED
    return JobStatus.PASSED


def refresh_running_jobs(
    body: str,
    api_jobs: dict[str, dict[str, JsonValue]],
    run_url: str,
) -> str:
    """Refresh live job states from the Actions API snapshot."""
    updated = body
    observed: list[JobStatus] = []
    for definition in workflow_jobs().values():
        api_job = api_jobs.get(definition.title)
        status = api_job_status(api_job) if api_job is not None else JobStatus.WAITING
        row = re.compile(
            rf"^(?P<prefix>\| {re.escape(definition.title)} \|) [^|]+(?P<suffix>\|.*)$",
            re.MULTILINE,
        )
        updated = row.sub(
            rf"\g<prefix> {status.label} \g<suffix>",
            updated,
            count=1,
        )
        logs_url = (
            optional_string(api_job.get("html_url")) if api_job is not None else None
        ) or run_url
        logs_link = re.compile(
            rf"^(\| {re.escape(definition.title)} \|.*\[Summary\]\([^)]+\) · )"
            r"\[Logs\]\([^)]+\)( \|)$",
            re.MULTILINE,
        )
        updated = logs_link.sub(
            partial(render_logs_link, logs_url=logs_url),
            updated,
            count=1,
        )
        observed.append(status)
    status = aggregate_status(observed)
    return re.sub(
        r"^## .* Quality Graph$",
        f"## {status.emoji} Quality Graph",
        updated,
        count=1,
        flags=re.MULTILINE,
    )


def render_logs_link(match: re.Match[str], *, logs_url: str) -> str:
    """Replace one dashboard details link with a concrete workflow job URL."""
    return f"{match.group(1)}[Logs]({logs_url}){match.group(2)}"


def mark_jobs_pending(github: GitHubAPI, number: int, job_ids: set[str]) -> None:
    """Mark selected dashboard rows pending without disturbing their controls."""
    comment = managed_comment(github, number, DASHBOARD_MARKER)
    if comment is None:
        message = "Cannot mark jobs pending without a Quality Graph dashboard"
        raise RuntimeError(message)
    body = string_value(comment.get("body"), "dashboard body")
    updated = re.sub(
        r"^## .* Quality Graph$",
        f"## {JobStatus.IN_PROGRESS.emoji} Quality Graph",
        body,
        count=1,
        flags=re.MULTILINE,
    )
    definitions = workflow_jobs()
    for job_id in job_ids:
        definition = definitions.get(job_id)
        if definition is None:
            continue
        row = re.compile(
            rf"^(\| {re.escape(definition.title)} \|) [^|]+(\|.*)$",
            re.MULTILINE,
        )
        updated = row.sub(
            rf"\1 {JobStatus.IN_PROGRESS.emoji} {JobStatus.IN_PROGRESS.value} \2", updated
        )
    unwrapped = MANAGED_MARKER_RE.sub("", updated)
    upsert_comment(github, number, DASHBOARD_MARKER, unwrapped)


def dashboard_metric(result: JobResult | None) -> str:
    """Render a Markdown-safe compact metric cell for one job result."""
    if result is None:
        return "—"
    return (
        " · ".join(
            f"{item.label.replace('|', '&#124;')}: {item.value.replace('|', '&#124;')}"
            for item in result.metrics[:2]
        )
        or "—"
    )


def update_dashboard_notice(github: GitHubAPI, number: int, message: str) -> None:
    """Replace only the command notice in the existing dashboard."""
    comment = managed_comment(github, number, DASHBOARD_MARKER)
    if comment is None:
        return
    body = string_value(comment.get("body"), "dashboard body")
    notice = f"<!-- monori-qg-notice:start -->\n{message}\n<!-- monori-qg-notice:end -->"
    updated = NOTICE_RE.sub(lambda _: notice, body, count=1)
    unwrapped = MANAGED_MARKER_RE.sub("", updated)
    upsert_comment(github, number, DASHBOARD_MARKER, unwrapped)


def api_job_status(job: dict[str, JsonValue]) -> JobStatus:
    """Map one Actions API job state to the dashboard domain."""
    if job.get("status") == "in_progress":
        return JobStatus.IN_PROGRESS
    if job.get("status") != "completed":
        return JobStatus.WAITING
    conclusion = optional_string(job.get("conclusion"))
    if conclusion == "success":
        return JobStatus.PASSED
    if conclusion == "skipped":
        return JobStatus.SKIPPED
    return JobStatus.FAILED


@dataclass(frozen=True)
class DashboardLifecycle:
    """Own race-safe publication of the single Quality Graph comment."""

    github: GitHubAPI
    number: int
    run_id: int
    run_attempt: int
    head_sha: str
    run_url: str

    def start(self) -> None:
        """Publish an in-progress dashboard while preserving existing controls."""
        if not self._head_is_current() or not self._is_latest_run():
            return
        existing = managed_comment(self.github, self.number, DASHBOARD_MARKER)
        body = optional_string(existing.get("body")) if existing is not None else ""
        controls = controls_from_markdown(body or "")
        api_jobs = self._api_jobs(required=False)
        jobs = tuple(
            DashboardJob(
                definition.job_id,
                definition.title,
                (
                    JobStatus.IN_PROGRESS
                    if definition.job_id == "workflow-graph"
                    else api_job_status(api_jobs[definition.title])
                    if definition.title in api_jobs
                    else JobStatus.WAITING
                ),
                f"{self.run_url}#{definition.summary_anchor}",
                (
                    optional_string(api_jobs[definition.title].get("html_url"))
                    if definition.title in api_jobs
                    else None
                )
                or self.run_url,
            )
            for definition in workflow_jobs().values()
        )
        groups = (
            (DashboardControlGroup("existing", "Current approvals", controls),) if controls else ()
        )
        self._publish(
            DashboardModel(
                JobStatus.IN_PROGRESS,
                "The current Quality Graph run is in progress.",
                self.run_id,
                self.run_attempt,
                self.head_sha,
                jobs,
                groups,
            )
        )
        delete_managed_comments(self.github, self.number, LEGACY_REPORT_MARKERS)

    def watch(self, poll_interval: float, timeout: float) -> None:
        """Continuously publish Actions job states through one dashboard writer."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._head_is_current() or not self._is_latest_run():
                return
            api_jobs = self._api_jobs(required=False)
            comment = managed_comment(self.github, self.number, DASHBOARD_MARKER)
            if comment is None:
                return
            body = string_value(comment.get("body"), "dashboard body")
            updated = refresh_running_jobs(body, api_jobs, self.run_url)
            upsert_comment(
                self.github,
                self.number,
                DASHBOARD_MARKER,
                MANAGED_MARKER_RE.sub("", updated),
            )
            if self._all_jobs_complete(api_jobs):
                return
            time.sleep(poll_interval)
        message = f"Quality Graph dashboard watcher timed out after {timeout:g} seconds"
        raise TimeoutError(message)

    def finish(self, results_directory: Path) -> None:
        """Publish final job states unless this workflow result is stale."""
        if not self._may_publish_final():
            return
        results = load_results(results_directory)
        api_jobs = self._api_jobs()
        rows: list[DashboardJob] = []
        control_groups: list[DashboardControlGroup] = []
        for definition in workflow_jobs().values():
            api_job = api_jobs.get(definition.title)
            result = results.get(definition.job_id)
            status = api_job_status(api_job) if api_job is not None else JobStatus.SKIPPED
            if result is not None and status is JobStatus.PASSED:
                status = result.status
            job_url = (
                optional_string(api_job.get("html_url")) if api_job is not None else None
            ) or self.run_url
            metric = dashboard_metric(result)
            rows.append(
                DashboardJob(
                    definition.job_id,
                    definition.title,
                    status,
                    f"{self.run_url}#{definition.summary_anchor}",
                    job_url,
                    metric,
                )
            )
            if result is not None and result.controls:
                control_groups.append(
                    DashboardControlGroup(
                        definition.job_id,
                        definition.title,
                        result.controls,
                        result.control_notes,
                    )
                )
        model = DashboardModel(
            dashboard_status(rows),
            "Detailed diagnostics and metrics are available in each job summary.",
            self.run_id,
            self.run_attempt,
            self.head_sha,
            tuple(rows),
            tuple(control_groups),
        )
        self._publish(model)
        if self._has_pending_command():
            if self._is_latest_run():
                self.start()
            else:
                self._restore_latest_run()
        elif not self._is_latest_run():
            self._restore_latest_run()

    def fail(self, message: str) -> None:
        """Mark the current dashboard failed when final aggregation cannot complete."""
        if not self._head_is_current() or not self._is_latest_run():
            return
        comment = managed_comment(self.github, self.number, DASHBOARD_MARKER)
        if comment is None:
            return
        body = string_value(comment.get("body"), "dashboard body")
        updated = re.sub(
            r"^## .* Quality Graph$",
            f"## {JobStatus.FAILED.emoji} Quality Graph",
            body,
            count=1,
            flags=re.MULTILINE,
        )
        notice = (
            "<!-- monori-qg-notice:start -->\n"
            f"{JobStatus.FAILED.emoji} {message}\n"
            "<!-- monori-qg-notice:end -->"
        )
        updated = NOTICE_RE.sub(lambda _: notice, updated, count=1)
        upsert_comment(
            self.github,
            self.number,
            DASHBOARD_MARKER,
            MANAGED_MARKER_RE.sub("", updated),
        )

    def _publish(self, model: DashboardModel) -> None:
        """Create or replace the bot-owned dashboard comment."""
        upsert_comment(self.github, self.number, DASHBOARD_MARKER, render_dashboard(model))

    def _head_is_current(self) -> bool:
        """Return whether the pull request still points at this workflow SHA."""
        pull = object_value(self.github.request("GET", f"/pulls/{self.number}"), "pull request")
        head = object_value(pull.get("head", {}), "pull request head")
        return head.get("sha") == self.head_sha

    def _may_publish_final(self) -> bool:
        """Reject stale runs and runs superseded by an administrator command."""
        return self._head_is_current() and self._is_latest_run() and not self._has_pending_command()

    def _is_latest_run(self) -> bool:
        """Return whether this run is the latest Quality Graph run for the PR head."""
        latest = self._latest_run()
        if latest is None:
            return True
        latest_id = latest.get("id")
        attempt = latest.get("run_attempt")
        if not isinstance(latest_id, int):
            return False
        if self.run_id != latest_id:
            return self.run_id > latest_id
        return attempt is None or (isinstance(attempt, int) and self.run_attempt >= attempt)

    def _latest_run(self) -> dict[str, JsonValue] | None:
        """Return the latest Quality Graph run associated with this pull request."""
        response = object_value(
            self.github.request(
                "GET",
                "/actions/workflows/pr-checks.yaml/runs"
                f"?event=pull_request&per_page={GITHUB_PAGE_SIZE}&page=1",
            ),
            "workflow runs response",
        )
        runs = [
            object_value(item, "workflow run")
            for item in array_value(response.get("workflow_runs", []), "workflow runs")
            if isinstance(item, dict)
            and (item.get("head_sha") == self.head_sha or self._run_has_pull(item))
        ]
        if not runs:
            return None
        return max(runs, key=lambda run: optional_string(run.get("created_at")) or "")

    def _restore_latest_run(self) -> None:
        """Restore the pending dashboard for a run that superseded this publisher."""
        latest = self._latest_run()
        if latest is None:
            return
        run_id = latest.get("id")
        attempt = latest.get("run_attempt", 1)
        head_sha = latest.get("head_sha")
        run_url = latest.get("html_url")
        if (
            isinstance(run_id, int)
            and isinstance(attempt, int)
            and isinstance(head_sha, str)
            and isinstance(run_url, str)
        ):
            DashboardLifecycle(
                self.github,
                self.number,
                run_id,
                attempt,
                head_sha,
                run_url,
            ).start()

    def _run_has_pull(self, run: dict[str, JsonValue]) -> bool:
        """Return whether an Actions run explicitly references this pull request."""
        return any(
            object_value(item, "workflow pull request").get("number") == self.number
            for item in array_value(run.get("pull_requests", []), "workflow pull requests")
        )

    def _has_pending_command(self) -> bool:
        """Return whether any registered gate has an unconsumed command marker."""
        pull = object_value(self.github.request("GET", f"/pulls/{self.number}"), "pull request")
        body = optional_string(pull.get("body")) or ""
        return any(
            check.approval_lifecycle.pending_pattern is not None
            and check.approval_lifecycle.pending_pattern.search(body) is not None
            for check in registered_checks().values()
        )

    @staticmethod
    def _all_jobs_complete(api_jobs: dict[str, dict[str, JsonValue]]) -> bool:
        """Return whether every dashboard check has reached a terminal Actions state."""
        return all(
            definition.title in api_jobs and api_jobs[definition.title].get("status") == "completed"
            for definition in workflow_jobs().values()
        )

    def _api_jobs(self, *, required: bool = True) -> dict[str, dict[str, JsonValue]]:
        """Load current workflow jobs indexed by their display name."""
        response = object_value(
            self.github.request(
                "GET", f"/actions/runs/{self.run_id}/jobs?per_page={GITHUB_PAGE_SIZE}&page=1"
            ),
            "workflow jobs response",
        )
        jobs = {
            string_value(job.get("name"), "workflow job name"): job
            for item in array_value(response.get("jobs", []), "workflow jobs")
            for job in (object_value(item, "workflow job"),)
        }
        if required and not jobs:
            message = f"Workflow run {self.run_id} returned no jobs"
            raise RuntimeError(message)
        return jobs


def main() -> int:
    """Publish the start or final state of the current dashboard."""
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("start", "watch", "finish", "fail"))
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_WATCH_INTERVAL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_WATCH_TIMEOUT)
    parser.add_argument("--message", default="The final dashboard could not be assembled.")
    args = parser.parse_args()
    lifecycle = DashboardLifecycle(
        GitHub(),
        args.pr_number,
        args.run_id,
        args.run_attempt,
        args.head_sha,
        args.run_url,
    )
    if args.operation == "start":
        lifecycle.start()
    elif args.operation == "watch":
        lifecycle.watch(args.poll_interval, args.timeout)
    elif args.operation == "fail":
        lifecycle.fail(args.message)
    elif args.results is None:
        parser.error("--results is required for finish")
    else:
        lifecycle.finish(args.results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
