"""Check changed Python annotations for uses of the overly broad ``object`` type."""

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

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

BOT_MARKER = "<!-- monori-object-annotation-gate -->"
BOT_LOGIN = "github-actions[bot]"
STATE_RE = re.compile(r"<!-- monori-object-annotation-state: (.+?) -->")
COMMAND_RE = re.compile(r"^/(ignore-all|ignore-file|ignore-object|remove-ignore)(?:\s+(\S+))?$")
PATCH_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
REQUEST_TIMEOUT = 30


def decode_json(data: bytes | str) -> JsonValue:
    value: JsonValue = json.loads(data)
    return value


def json_object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object for {context}")
    return value


def json_array(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise RuntimeError(f"Expected a JSON array for {context}")
    return value


def json_string(value: JsonValue, context: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"Expected a JSON string for {context}")
    return value


def json_integer(value: JsonValue, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"Expected a JSON integer for {context}")
    return value


def optional_string(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def parse_command(body: str) -> tuple[str, str | None] | None:
    match = COMMAND_RE.fullmatch(body)
    if not match:
        return None
    name, argument = match.groups()
    if name == "ignore-all":
        return (name, None) if argument is None else None
    return (name, argument) if argument else None


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    annotation: str
    finding_id: str


class GitHubAPIError(RuntimeError):
    def __init__(self, method: str, path: str, status: int) -> None:
        super().__init__(f"GitHub API {method} {path} failed: HTTP {status}")
        self.status = status


class GitHub:
    def __init__(self) -> None:
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
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
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 204:
                    return None
                return decode_json(response.read())
        except urllib.error.HTTPError as error:
            if method == "GET" and error.code == 404:
                return None
            raise GitHubAPIError(method, path, error.code) from error
        except (TimeoutError, urllib.error.URLError) as error:
            raise RuntimeError(f"GitHub API {method} {path} failed: {error}") from error

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        result: list[dict[str, JsonValue]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            response = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            items = json_array(response, path)
            result.extend(json_object(item, path) for item in items)
            if len(items) < 100:
                return result
            page += 1

    def file_text(self, path: str, ref: str) -> str | None:
        encoded = urllib.parse.quote(path, safe="")
        raw_response = self.request("GET", f"/contents/{encoded}?ref={urllib.parse.quote(ref)}")
        if raw_response is None:
            return None
        response = json_object(raw_response, path)
        if response.get("encoding") == "base64" and response.get("content"):
            content = json_string(response["content"], f"{path}.content")
            return base64.b64decode(content).decode("utf-8")
        download_url = optional_string(response.get("download_url"))
        if not download_url:
            raise RuntimeError(f"Cannot read {path} at {ref}")
        request = urllib.request.Request(
            download_url,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as result:
            text: str = result.read().decode("utf-8")
            return text


def changed_lines(before: str | None, after: str) -> set[int]:
    before_lines = [] if before is None else before.splitlines()
    after_lines = after.splitlines()
    changed: set[int] = set()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    for tag, _, _, new_start, new_end in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            changed.update(range(new_start + 1, new_end + 1))
    return changed


def added_lines_from_patch(patch: str) -> set[int]:
    added: set[int] = set()
    new_line = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            match = PATCH_HUNK_RE.match(line)
            if not match:
                raise RuntimeError(f"Cannot parse diff hunk: {line}")
            new_line = int(match.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            added.add(new_line)
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif new_line:
            new_line += 1
    return added


def annotation_nodes(tree: ast.AST) -> list[ast.expr]:
    nodes: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            arguments.extend(
                argument for argument in (node.args.vararg, node.args.kwarg) if argument
            )
            nodes.extend(argument.annotation for argument in arguments if argument.annotation)
            if node.returns:
                nodes.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            nodes.append(node.annotation)
    return nodes


def contains_object(annotation: ast.expr) -> tuple[int, int] | None:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id == "object":
            return node.lineno, node.col_offset
        if isinstance(node, ast.Attribute) and node.attr == "object":
            return node.lineno, node.col_offset
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                parsed = ast.parse(node.value, mode="eval")
            except SyntaxError:
                continue
            if contains_object(parsed.body):
                return node.lineno, node.col_offset
    return None


def scan_file(path: str, source: str, changed: set[int]) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        print(
            f"::error file={path},line={error.lineno or 1}::Cannot parse Python file: {error}",
            file=sys.stderr,
        )
        return []

    findings: list[Finding] = []
    for annotation in annotation_nodes(tree):
        object_location = contains_object(annotation)
        if object_location is None or object_location[0] not in changed:
            continue
        object_line, object_column = object_location
        rendered = ast.unparse(annotation)
        raw_id = f"{path}:{object_line}:{object_column}:{rendered}"
        finding_id = hashlib.sha256(raw_id.encode()).hexdigest()[:12]
        findings.append(Finding(path, object_line, object_column, rendered, finding_id))
    return sorted(findings, key=lambda finding: (finding.line, finding.column, finding.annotation))


def parse_state(body: str, sha: str) -> set[str]:
    match = STATE_RE.search(body)
    if not match:
        return set()
    try:
        state = json_object(decode_json(match.group(1)), "annotation state")
    except json.JSONDecodeError:
        return set()
    if state.get("sha") != sha:
        return set()
    approved = json_array(state.get("approved", []), "approved findings")
    return {json_string(item, "approved finding") for item in approved}


def state_marker(sha: str, approved: set[str]) -> str:
    state = json.dumps({"sha": sha, "approved": sorted(approved)}, separators=(",", ":"))
    return f"{BOT_MARKER}\n<!-- monori-object-annotation-state: {state} -->"


def finding_url(pr_url: str, finding: Finding) -> str:
    diff_hash = hashlib.sha256(finding.path.encode()).hexdigest()
    return f"{pr_url}/changes#diff-{diff_hash}R{finding.line}"


def comment_body(findings: list[Finding], sha: str, approved: set[str], pr_url: str) -> str:
    active = [finding for finding in findings if finding.finding_id not in approved]
    status = "✅" if not active else "❌"
    lines = [
        state_marker(sha, approved),
        f"## {status} Python <code>object</code> annotation check",
        "This check finds newly added Python annotations that use the broad `object` type.",
        "Please replace each finding with a specific type, or ask an administrator to approve it.",
        "",
        "<details>",
        f"<summary>List of problems ({len(findings)})</summary>",
        "",
    ]
    for finding in findings:
        marker = "✔" if finding.finding_id in approved else "✗"
        location = f"{finding.path}:{finding.line}"
        lines.append(
            f"- {marker} [`{location}`]({finding_url(pr_url, finding)}) "
            f"— `{finding.annotation}` · `{finding.finding_id}`"
        )
    lines.append("</details>")
    lines.extend(
        [
            "",
            "<details>",
            "<summary>For admins</summary>",
            "",
            "Post exactly one command as a new comment to manage approvals:",
            "",
            "| Command | Purpose |",
            "| --- | --- |",
            "| `/ignore-object <finding-id>` | Approve one finding. |",
            "| `/ignore-file path/to/file.py` | Approve all findings in a file. |",
            "| `/ignore-all` | Approve all findings in the pull request. |",
            "| `/remove-ignore <finding-id>` | Remove an approval. |",
            "",
            "</details>",
        ]
    )
    return "\n".join(lines)


def find_bot_comment(github: GitHub, number: int) -> dict[str, JsonValue] | None:
    comments = github.paged(f"/issues/{number}/comments")
    return next(
        (
            comment
            for comment in comments
            if json_object(comment.get("user", {}), "comment user").get("login") == BOT_LOGIN
            and json_object(comment.get("user", {}), "comment user").get("type") == "Bot"
            and BOT_MARKER in (optional_string(comment.get("body")) or "")
        ),
        None,
    )


def update_bot_comment(
    github: GitHub,
    number: int,
    body: str,
    existing: dict[str, JsonValue] | None,
) -> None:
    if existing:
        comment_id = json_integer(existing["id"], "comment id")
        github.request("PATCH", f"/issues/comments/{comment_id}", {"body": body})
    else:
        github.request("POST", f"/issues/{number}/comments", {"body": body})


def delete_bot_comment(github: GitHub, existing: dict[str, JsonValue] | None) -> None:
    if existing:
        comment_id = json_integer(existing["id"], "comment id")
        github.request("DELETE", f"/issues/comments/{comment_id}")


def is_admin(github: GitHub, login: str) -> bool:
    encoded = urllib.parse.quote(login, safe="")
    try:
        permission = github.request("GET", f"/collaborators/{encoded}/permission")
    except GitHubAPIError as error:
        if error.status == 403:
            return False
        raise
    if permission is None:
        return False
    return json_object(permission, "collaborator permission").get("permission") == "admin"


def pull_request_number(event: dict[str, JsonValue]) -> int | None:
    if event.get("pull_request"):
        pull = json_object(event["pull_request"], "event pull request")
        return json_integer(pull["number"], "pull request number")
    issue = json_object(event.get("issue", {}), "event issue")
    return json_integer(issue["number"], "issue number") if issue.get("pull_request") else None


def scan_pull_request(github: GitHub, pull: dict[str, JsonValue]) -> list[Finding]:
    head = json_object(pull["head"], "pull request head")
    base = json_object(pull["base"], "pull request base")
    number = json_integer(pull["number"], "pull request number")
    head_sha = json_string(head["sha"], "head sha")
    base_sha = json_string(base["sha"], "base sha")
    files = github.paged(f"/pulls/{number}/files")
    raw_comparison = github.request("GET", f"/compare/{base_sha}...{head_sha}")
    if raw_comparison is None:
        raise RuntimeError(f"Cannot determine merge base for pull request #{number}")
    comparison = json_object(raw_comparison, "pull request comparison")
    merge_commit = json_object(comparison["merge_base_commit"], "merge base commit")
    merge_base = json_string(merge_commit["sha"], "merge base sha")
    findings: list[Finding] = []
    for file in files:
        path = json_string(file["filename"], "changed filename")
        if not path.endswith(".py") or file["status"] == "removed":
            continue
        source = github.file_text(path, head_sha)
        if source is None:
            raise RuntimeError(f"Cannot read changed Python file {path} at {head_sha}")
        patch = optional_string(file.get("patch"))
        if patch:
            changed = added_lines_from_patch(patch)
        else:
            before_path = optional_string(file.get("previous_filename")) or path
            before = github.file_text(before_path, merge_base)
            changed = changed_lines(before, source)
        findings.extend(scan_file(path, source, changed))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.column))


def rerun_pull_request_gate(github: GitHub, number: int) -> None:
    raw_response = github.request(
        "GET",
        "/actions/workflows/object-annotation-gate.yaml/runs?event=pull_request_target&per_page=100",
    )
    if raw_response is None:
        runs: list[dict[str, JsonValue]] = []
    else:
        response = json_object(raw_response, "workflow runs")
        raw_runs = json_array(response.get("workflow_runs", []), "workflow runs")
        runs = [json_object(run, "workflow run") for run in raw_runs]
    matching = [
        run
        for run in runs
        if any(
            json_object(pull_request, "workflow pull request").get("number") == number
            for pull_request in json_array(run.get("pull_requests", []), "workflow pull requests")
        )
    ]
    if not matching:
        raise RuntimeError(f"Cannot find a previous gate run for pull request #{number}")
    latest = max(matching, key=lambda run: optional_string(run.get("created_at")) or "")
    run_id = json_integer(latest["id"], "workflow run id")
    github.request("POST", f"/actions/runs/{run_id}/rerun")


def main() -> int:
    github = GitHub()
    event = json_object(
        decode_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()), "GitHub event"
    )
    number = pull_request_number(event)
    if number is None:
        return 0

    raw_pull = github.request("GET", f"/pulls/{number}")
    if raw_pull is None:
        raise RuntimeError(f"Pull request #{number} was not found")
    pull = json_object(raw_pull, "pull request")
    findings = scan_pull_request(github, pull)
    head = json_object(pull["head"], "pull request head")
    sha = json_string(head["sha"], "head sha")
    existing = find_bot_comment(github, number)
    approved = parse_state(optional_string(existing.get("body")) or "", sha) if existing else set()

    comment = json_object(event.get("comment", {}), "event comment")
    command = parse_command((optional_string(comment.get("body")) or "").strip())
    state_changed = False
    if command:
        command_name, command_argument = command
        author_data = json_object(comment["user"], "comment user")
        author = json_string(author_data["login"], "comment author")
        if not is_admin(github, author):
            print(f"{author} is not a repository administrator; approval ignored")
        else:
            finding_ids = {finding.finding_id for finding in findings}
            if command_name == "ignore-all" and command_argument is None:
                approved.update(finding_ids)
                state_changed = True
            elif command_name == "ignore-file" and command_argument:
                file_ids = {
                    finding.finding_id for finding in findings if finding.path == command_argument
                }
                if file_ids:
                    approved.update(file_ids)
                    state_changed = True
                else:
                    print(
                        f"{command_argument} is not an active Python file in {sha};"
                        " approval ignored"
                    )
            elif command_name in {"ignore-object", "remove-ignore"} and command_argument:
                if command_argument not in finding_ids:
                    print(f"{command_argument} is not an active finding for {sha}; command ignored")
                elif command_name == "ignore-object":
                    approved.add(command_argument)
                    state_changed = True
                elif command_argument in approved:
                    approved.remove(command_argument)
                    state_changed = True
            else:
                print(f"Invalid {command_name} command; command ignored")

    if not findings:
        delete_bot_comment(github, existing)
        return 0

    pr_url = json_string(pull["html_url"], "pull request URL")
    update_bot_comment(
        github,
        number,
        comment_body(findings, sha, approved, pr_url),
        existing,
    )
    unapproved = [finding for finding in findings if finding.finding_id not in approved]
    if state_changed:
        rerun_pull_request_gate(github, number)
    if unapproved:
        for finding in unapproved:
            print(
                f"::error file={finding.path},line={finding.line},"
                f"col={finding.column + 1}::Use a specific type instead of object"
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
