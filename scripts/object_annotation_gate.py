"""Check changed Python annotations for uses of the overly broad ``object`` type."""

from __future__ import annotations

import ast
import base64
import difflib
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BOT_MARKER = "<!-- monori-object-annotation-gate -->"
STATE_RE = re.compile(r"<!-- monori-object-annotation-state: (.+?) -->")
COMMAND_RE = re.compile(r"^/ignore-object\s+([a-z0-9]+)$")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    annotation: str
    finding_id: str


class GitHub:
    def __init__(self) -> None:
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: Any = None) -> Any:
        url = f"{self.base_url}/repos/{self.repository}{path}"
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            url,
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
            with urllib.request.urlopen(request) as response:
                if response.status == 204:
                    return None
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {error.code}") from error

    def paged(self, path: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            items = self.request("GET", f"{path}{separator}per_page=100&page={page}") or []
            result.extend(items)
            if len(items) < 100:
                return result
            page += 1

    def file_text(self, path: str, ref: str) -> str | None:
        encoded = urllib.parse.quote(path, safe="")
        response = self.request("GET", f"/contents/{encoded}?ref={urllib.parse.quote(ref)}")
        if response is None:
            return None
        if response.get("encoding") == "base64" and response.get("content"):
            return base64.b64decode(response["content"]).decode("utf-8")
        download_url = response.get("download_url")
        if not download_url:
            raise RuntimeError(f"Cannot read {path} at {ref}")
        request = urllib.request.Request(
            download_url,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with urllib.request.urlopen(request) as result:
            return result.read().decode("utf-8")


def changed_lines(before: str | None, after: str) -> set[int]:
    before_lines = [] if before is None else before.splitlines()
    after_lines = after.splitlines()
    changed: set[int] = set()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    for tag, _, _, new_start, new_end in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            changed.update(range(new_start + 1, new_end + 1))
    return changed


def annotation_nodes(tree: ast.AST) -> list[ast.expr]:
    nodes: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            arguments.extend(argument for argument in (node.args.vararg, node.args.kwarg) if argument)
            nodes.extend(argument.annotation for argument in arguments if argument.annotation)
            if node.returns:
                nodes.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            nodes.append(node.annotation)
    return nodes


def contains_object(annotation: ast.expr) -> ast.Name | None:
    return next(
        (node for node in ast.walk(annotation) if isinstance(node, ast.Name) and node.id == "object"),
        None,
    )


def scan_file(path: str, source: str, changed: set[int]) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        print(f"::error file={path},line={error.lineno or 1}::Cannot parse Python file: {error}", file=sys.stderr)
        return []

    findings: list[Finding] = []
    for annotation in annotation_nodes(tree):
        object_node = contains_object(annotation)
        if object_node is None or object_node.lineno not in changed:
            continue
        rendered = ast.unparse(annotation)
        raw_id = f"{path}:{object_node.lineno}:{object_node.col_offset}:{rendered}"
        finding_id = hashlib.sha256(raw_id.encode()).hexdigest()[:12]
        findings.append(
            Finding(path, object_node.lineno, object_node.col_offset, rendered, finding_id)
        )
    return sorted(findings, key=lambda finding: (finding.line, finding.column, finding.annotation))


def parse_state(body: str, sha: str) -> set[str]:
    match = STATE_RE.search(body)
    if not match:
        return set()
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError:
        return set()
    return set(state.get("approved", [])) if state.get("sha") == sha else set()


def state_marker(sha: str, approved: set[str]) -> str:
    state = json.dumps({"sha": sha, "approved": sorted(approved)}, separators=(",", ":"))
    return f"{BOT_MARKER}\n<!-- monori-object-annotation-state: {state} -->"


def comment_body(findings: list[Finding], sha: str, approved: set[str]) -> str:
    active = [finding for finding in findings if finding.finding_id not in approved]
    status = "✅ All findings are approved for this commit." if not active else "❌ Unapproved findings remain."
    lines = [state_marker(sha, approved), "## Python `object` annotation check", "", status, ""]
    for finding in findings:
        marker = "approved" if finding.finding_id in approved else "not approved"
        lines.append(f"- `{finding.finding_id}` — `{finding.path}:{finding.line}` ({marker}): `{finding.annotation}`")
    if active:
        lines.extend(
            [
                "",
                "If an exception is justified, a repository administrator may approve one finding with:",
                "",
                "```text",
                f"/ignore-object {active[0].finding_id}",
                "```",
            ]
        )
    return "\n".join(lines)


def find_bot_comment(github: GitHub, number: int) -> dict[str, Any] | None:
    comments = github.paged(f"/issues/{number}/comments")
    return next((comment for comment in comments if BOT_MARKER in comment.get("body", "")), None)


def update_bot_comment(github: GitHub, number: int, body: str, existing: dict[str, Any] | None) -> None:
    if existing:
        github.request("PATCH", f"/issues/comments/{existing['id']}", {"body": body})
    else:
        github.request("POST", f"/issues/{number}/comments", {"body": body})


def delete_bot_comment(github: GitHub, existing: dict[str, Any] | None) -> None:
    if existing:
        github.request("DELETE", f"/issues/comments/{existing['id']}")


def is_admin(github: GitHub, login: str) -> bool:
    encoded = urllib.parse.quote(login, safe="")
    permission = github.request("GET", f"/collaborators/{encoded}/permission")
    return bool(permission and permission.get("permission") == "admin")


def pull_request_number(event: dict[str, Any]) -> int | None:
    if event.get("pull_request"):
        return event["pull_request"]["number"]
    issue = event.get("issue", {})
    return issue.get("number") if issue.get("pull_request") else None


def scan_pull_request(github: GitHub, pull: dict[str, Any]) -> list[Finding]:
    head = pull["head"]
    base = pull["base"]
    files = github.paged(f"/pulls/{pull['number']}/files")
    findings: list[Finding] = []
    for file in files:
        path = file["filename"]
        if not path.endswith(".py") or file["status"] == "removed":
            continue
        source = github.file_text(path, head["sha"])
        if source is None:
            continue
        before_path = file.get("previous_filename", path)
        before = github.file_text(before_path, base["sha"])
        findings.extend(scan_file(path, source, changed_lines(before, source)))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.column))


def main() -> int:
    github = GitHub()
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    number = pull_request_number(event)
    if number is None:
        return 0

    pull = github.request("GET", f"/pulls/{number}")
    if pull is None:
        raise RuntimeError(f"Pull request #{number} was not found")
    findings = scan_pull_request(github, pull)
    sha = pull["head"]["sha"]
    existing = find_bot_comment(github, number)
    approved = parse_state(existing.get("body", ""), sha) if existing else set()

    if event.get("comment") and COMMAND_RE.fullmatch(event["comment"].get("body", "").strip()):
        finding_id = COMMAND_RE.fullmatch(event["comment"]["body"].strip()).group(1)  # type: ignore[union-attr]
        author = event["comment"]["user"]["login"]
        if not is_admin(github, author):
            print(f"{author} is not a repository administrator; approval ignored")
        elif finding_id not in {finding.finding_id for finding in findings}:
            print(f"{finding_id} is not an active finding for {sha}; approval ignored")
        else:
            approved.add(finding_id)

    if not findings:
        delete_bot_comment(github, existing)
        return 0

    update_bot_comment(github, number, comment_body(findings, sha, approved), existing)
    unapproved = [finding for finding in findings if finding.finding_id not in approved]
    if unapproved:
        for finding in unapproved:
            print(f"::error file={finding.path},line={finding.line},col={finding.column + 1}::Use a specific type instead of object")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
