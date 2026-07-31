#!/usr/bin/env python3
"""
Run the issue #197 typing migration as isolated ya code jobs.

The script deliberately never pushes or deletes a worktree.  Failed attempts
remain below .worktrees/issue197/ together with their logs and can be inspected
or resumed manually.  Run `python3 scripts/issue197_agents.py --help`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import selectors
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict

MODELS = (
    "eliza-glm-5-2/glm-5-2",
    "eliza-minimax/minimax-latest",
    "eliza-glm-latest/glm-latest",
)
STATE_DIR = Path(".issue197")
STATE_FILE = STATE_DIR / "state.json"
WORKTREE_DIR = Path(".worktrees/issue197")
TASKS_FILE = Path("scripts/issue197_tasks.json")
ATTEMPT_TIMEOUT_SECONDS = 60 * 60
INACTIVITY_TIMEOUT_SECONDS = 15 * 60
KILL_GRACE_SECONDS = 30


@dataclass(frozen=True)
class Task:
    key: str
    wave: int
    description: str
    paths: tuple[str, ...]


class TaskState(TypedDict):
    status: str
    attempts: int
    model: NotRequired[str]
    worktree: NotRequired[str]
    head: NotRequired[str]
    failure: NotRequired[str]
    integrated: NotRequired[bool]


class State(TypedDict):
    base: str
    deadline: float
    models: list[str]
    tasks: dict[str, TaskState]


def load_tasks(root: Path) -> tuple[Task, ...]:
    raw: object = json.loads((root / TASKS_FILE).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("task manifest must contain a list")
    tasks: list[Task] = []
    for item in raw:
        if not isinstance(item, dict):
            raise RuntimeError("task manifest contains a non-object")
        key = item.get("key")
        wave = item.get("wave")
        description = item.get("description")
        paths = item.get("paths")
        if (
            not isinstance(key, str)
            or not isinstance(wave, int)
            or not isinstance(description, str)
        ):
            raise RuntimeError("task manifest has invalid task metadata")
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            raise RuntimeError("task manifest has invalid paths")
        tasks.append(Task(key, wave, description, tuple(paths)))
    return tuple(tasks)


def run_command(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    completed = subprocess.run(args, cwd=cwd, check=check, text=True, capture_output=True)
    return completed.stdout.strip()


def repository_root() -> Path:
    return Path(run_command(["git", "rev-parse", "--show-toplevel"])).resolve()


def state_path(root: Path) -> Path:
    return root / STATE_FILE


def load_state(root: Path) -> State:
    path = state_path(root)
    if not path.exists():
        return {"tasks": {}, "base": "", "deadline": 0.0, "models": []}
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("state file must contain an object")
    base = raw.get("base")
    deadline = raw.get("deadline")
    models = raw.get("models")
    tasks = raw.get("tasks")
    if not isinstance(base, str) or not isinstance(deadline, (int, float)):
        raise RuntimeError("state file has an invalid base or deadline")
    if not isinstance(models, list) or not all(isinstance(model, str) for model in models):
        raise RuntimeError("state file has invalid models")
    if not isinstance(tasks, dict):
        raise RuntimeError("state file has invalid tasks")
    parsed_tasks: dict[str, TaskState] = {}
    for key, value in tasks.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise RuntimeError("state file has invalid task entries")
        status = value.get("status")
        attempts = value.get("attempts")
        if not isinstance(status, str) or not isinstance(attempts, int):
            raise RuntimeError("state file has invalid task status")
        parsed: TaskState = {"status": status, "attempts": attempts}
        for field in ("model", "worktree", "head", "failure"):
            field_value = value.get(field)
            if isinstance(field_value, str):
                parsed[field] = field_value
        integrated = value.get("integrated")
        if isinstance(integrated, bool):
            parsed["integrated"] = integrated
        parsed_tasks[key] = parsed
    return {"base": base, "deadline": float(deadline), "models": models, "tasks": parsed_tasks}


def save_state(root: Path, state: State) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def task_state(state: State, key: str) -> TaskState:
    return state["tasks"].get(key, {"status": "pending", "attempts": 0})


def task_prompt(task: Task, previous_failure: str) -> str:
    allowed = "\n".join(f"- `{path}`" for path in task.paths)
    retry_context = f"\nPrevious attempt failed: {previous_failure}\n" if previous_failure else ""
    return f"""Work on GitHub issue #197, static typing migration.

You own exactly this shard: {task.description}

Allowed paths:
{allowed}

Read AGENTS.md and existing code first. Convert owned JavaScript/JSX files and
their tests to TypeScript/TSX when applicable. Add real types; never add `Any`,
`@ts-ignore`, `@ts-nocheck`, broad suppressions, or casts merely to silence a
checker. Do not change runtime behaviour or public API JSON shapes. Do not edit
files outside the allowed paths; report a blocker instead.

Run the most focused relevant tests plus lint/type checks you can make meaningful.
Commit the completed work once with a descriptive message. If you cannot complete
it, leave a concise explanation in your final response and do not make unrelated
changes.
{retry_context}"""


def available_models(root: Path) -> tuple[str, ...]:
    output = run_command(["ya", "code", "opencode", "models"], cwd=root)
    available = set(output.splitlines())
    return tuple(model for model in MODELS if model in available)


def require_automation_tokens() -> None:
    missing = [name for name in ("ELIZA_TOKEN", "YA_TOKEN") if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"missing environment variable(s): {', '.join(missing)}")


def require_clean_root(root: Path) -> None:
    if run_command(["git", "status", "--porcelain"], cwd=root):
        raise RuntimeError(
            "working tree is dirty; commit or stash bootstrap changes before prepare"
        )


def prepare(root: Path) -> None:
    require_clean_root(root)
    require_automation_tokens()
    models = available_models(root)
    if not models:
        raise RuntimeError("none of the configured internal models is available")
    integration = "issue-197-integration"
    branches = run_command(["git", "branch", "--list", integration], cwd=root)
    if not branches:
        run_command(["git", "branch", integration, "HEAD"], cwd=root)
    state: State = {"base": integration, "deadline": 0.0, "models": list(models), "tasks": {}}
    save_state(root, state)
    print(f"prepared {len(load_tasks(root))} jobs from {integration}; models: {', '.join(models)}")


def dry_run(root: Path) -> None:
    tasks = load_tasks(root)
    keys = [task.key for task in tasks]
    if len(keys) != len(set(keys)):
        raise RuntimeError("task manifest has duplicate keys")
    backend = sum(task.key.startswith("back-") for task in tasks)
    frontend = sum(task.key.startswith("front-") for task in tasks)
    models = available_models(root)
    print(f"jobs: backend={backend}, frontend={frontend}, total={len(tasks)}")
    print(f"available fallback models: {', '.join(models) or 'none'}")
    for wave in sorted({task.wave for task in tasks}):
        print(f"wave {wave}: {sum(task.wave == wave for task in tasks)} job(s)")


def start_attempt(
    root: Path, task: Task, state: State, attempt: int
) -> tuple[subprocess.Popen[str], Path, Path, str]:
    model = state["models"][attempt % len(state["models"])]
    attempt_dir = root / WORKTREE_DIR / f"{task.key}-a{attempt + 1}"
    branch = f"issue-197/{task.key}-a{attempt + 1}"
    if attempt_dir.exists():
        raise RuntimeError(f"attempt worktree already exists: {attempt_dir}")
    run_command(["git", "worktree", "add", "-b", branch, str(attempt_dir), state["base"]], cwd=root)
    log_dir = root / STATE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{task.key}-a{attempt + 1}.jsonl"
    prior = task_state(state, task.key).get("failure", "")
    permission = json.dumps(
        {
            "*": "ask",
            "read": "allow",
            "edit": "allow",
            "write": "allow",
            "bash": {
                "*": "deny",
                "git status*": "allow",
                "git diff*": "allow",
                "git log*": "allow",
                "git ls-files*": "allow",
                "git mv*": "allow",
                "git add*": "allow",
                "git commit*": "allow",
                "rg *": "allow",
                "sed *": "allow",
                "find *": "allow",
                "make typecheck*": "allow",
                "npm run *": "allow",
                "npx vitest*": "allow",
                "uv run mypy*": "allow",
                "uv run ruff*": "allow",
                "uv run pytest*": "allow",
            },
        }
    )
    env = os.environ | {"OPENCODE_PERMISSION": permission}
    process = subprocess.Popen(
        [
            "ya",
            "code",
            "opencode",
            "run",
            "--model",
            model,
            "--format",
            "json",
            task_prompt(task, prior),
        ],
        cwd=attempt_dir,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return process, attempt_dir, log_path, model


def branch_head(worktree: Path) -> str:
    return run_command(["git", "rev-parse", "HEAD"], cwd=worktree)


def changed_paths(worktree: Path, base: str) -> tuple[str, ...]:
    output = run_command(["git", "diff", "--name-only", f"{base}..HEAD"], cwd=worktree)
    return tuple(path for path in output.splitlines() if path)


def changed_paths_are_allowed(task: Task, worktree: Path, base: str) -> tuple[bool, str]:
    outside = [
        path
        for path in changed_paths(worktree, base)
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in task.paths)
    ]
    if outside:
        return False, f"commit changed paths outside shard: {', '.join(outside)}"
    return True, ""


def successful_attempt(task: Task, worktree: Path, base: str) -> tuple[bool, str]:
    if run_command(["git", "status", "--porcelain"], cwd=worktree):
        return False, "agent left uncommitted changes"
    if branch_head(worktree) == run_command(["git", "rev-parse", base], cwd=worktree):
        return False, "agent exited without a commit"
    return changed_paths_are_allowed(task, worktree, base)


def run_wave(root: Path, concurrency: int, hours: float) -> None:
    state = load_state(root)
    tasks = load_tasks(root)
    if not state["base"]:
        raise RuntimeError("run prepare first")
    if state["deadline"] == 0.0:
        state["deadline"] = time.time() + hours * 3600
    pending = [task for task in tasks if task_state(state, task.key)["status"] != "success"]
    if not pending:
        print("all jobs are already successful")
        return
    wave = min(task.wave for task in pending)
    pending = [task for task in pending if task.wave == wave]
    print(f"running wave {wave} with {len(pending)} jobs, deadline {time.ctime(state['deadline'])}")
    active: dict[str, tuple[Task, subprocess.Popen[str], Path, Path, float, float, int, str]] = {}
    selector = selectors.DefaultSelector()
    next_task = 0
    while (next_task < len(pending) or active) and time.time() < state["deadline"]:
        while next_task < len(pending) and len(active) < concurrency:
            task = pending[next_task]
            next_task += 1
            existing = task_state(state, task.key)
            attempt = existing["attempts"]
            process, worktree, log_path, model = start_attempt(root, task, state, attempt)
            assert process.stdout is not None
            selector.register(process.stdout, selectors.EVENT_READ, task.key)
            now = time.time()
            active[task.key] = (task, process, worktree, log_path, now, now, attempt, model)
            state["tasks"][task.key] = {
                "status": "running",
                "attempts": attempt + 1,
                "model": model,
                "worktree": str(worktree),
            }
            save_state(root, state)
            print(f"started {task.key} attempt {attempt + 1} with {model}")
        for key, _ in selector.select(timeout=5):
            task_key = str(key.data)
            task, process, worktree, log_path, started, _, attempt, model = active[task_key]
            assert process.stdout is not None
            line = process.stdout.readline()
            if line:
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(line)
                active[task_key] = (
                    task,
                    process,
                    worktree,
                    log_path,
                    started,
                    time.time(),
                    attempt,
                    model,
                )
        for task_key, item in list(active.items()):
            task, process, worktree, log_path, started, last_event, attempt, model = item
            elapsed = time.time() - started
            inactive = time.time() - last_event
            return_code = process.poll()
            timed_out = elapsed > ATTEMPT_TIMEOUT_SECONDS or inactive > INACTIVITY_TIMEOUT_SECONDS
            if return_code is None and not timed_out:
                continue
            if return_code is None:
                process.terminate()
                try:
                    process.wait(timeout=KILL_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                failure = (
                    "attempt timed out"
                    if elapsed > ATTEMPT_TIMEOUT_SECONDS
                    else "attempt became inactive"
                )
            elif return_code == 0:
                succeeded, failure = successful_attempt(task, worktree, state["base"])
                if succeeded:
                    failure = ""
            else:
                failure = f"agent exited {return_code} without a clean commit"
            assert process.stdout is not None
            selector.unregister(process.stdout)
            del active[task_key]
            if not failure:
                state["tasks"][task_key] = {
                    "status": "success",
                    "attempts": attempt + 1,
                    "model": model,
                    "worktree": str(worktree),
                    "head": branch_head(worktree),
                }
                print(f"success {task_key}: {model}")
            else:
                state["tasks"][task_key] = {
                    "status": "pending",
                    "attempts": attempt + 1,
                    "failure": failure,
                    "model": model,
                    "worktree": str(worktree),
                }
                pending.append(task)
                print(f"retry {task_key}: {failure}")
            save_state(root, state)
    if active:
        print("deadline reached; active jobs were left running for manual recovery")
    save_state(root, state)


def integrate(root: Path) -> None:
    state = load_state(root)
    tasks = load_tasks(root)
    if not state["base"]:
        raise RuntimeError("run prepare first")
    successful = [task for task in tasks if task_state(state, task.key)["status"] == "success"]
    if not successful:
        raise RuntimeError("no successful jobs to integrate")
    integration_dir = root / WORKTREE_DIR / "integration"
    if not integration_dir.exists():
        run_command(["git", "worktree", "add", str(integration_dir), state["base"]], cwd=root)
    for task in successful:
        task_state = state["tasks"][task.key]
        if task_state.get("integrated"):
            continue
        try:
            run_command(["git", "cherry-pick", task_state["head"]], cwd=integration_dir)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"integration conflict in {task.key}; resolve it in {integration_dir}:\n"
                f"{error.stderr}"
            ) from error
        task_state["integrated"] = True
        save_state(root, state)
        print(f"integrated {task.key}")


def status(root: Path) -> None:
    state = load_state(root)
    for task in load_tasks(root):
        item = state["tasks"].get(task.key, {"status": "pending", "attempts": 0})
        print(
            f"{task.key:28} {item['status']:8} "
            f"attempts={item.get('attempts', 0)} model={item.get('model', '-')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("dry-run", "prepare", "run", "resume", "integrate", "status")
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--hours", type=float, default=10.0)
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")
    if args.hours <= 0:
        parser.error("--hours must be positive")
    root = repository_root()
    try:
        if args.command == "dry-run":
            dry_run(root)
        elif args.command == "prepare":
            prepare(root)
        elif args.command in {"run", "resume"}:
            run_wave(root, args.concurrency, args.hours)
        elif args.command == "integrate":
            integrate(root)
        else:
            status(root)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
