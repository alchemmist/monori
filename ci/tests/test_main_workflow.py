import json
import re
from typing import ClassVar, cast

import yaml

from monori.ci.tests.test_pr_workflow import REPOSITORY_ROOT, WorkflowDocument

WORKFLOW = REPOSITORY_ROOT / ".github/workflows/main-checks.yaml"
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/deploy.yaml"
PRODUCTION_COMPOSE = REPOSITORY_ROOT / "deploy/docker-compose.yml"
DOCKER_DAEMON_CONFIG = REPOSITORY_ROOT / "deploy/docker-daemon.json"
DOCKER_GC_SERVICE = REPOSITORY_ROOT / "deploy/systemd/docker-disk-gc.service"
DOCKER_GC_TIMER = REPOSITORY_ROOT / "deploy/systemd/docker-disk-gc.timer"


class TestMainWorkflowGraph:
    source: ClassVar[str]
    workflow: ClassVar[WorkflowDocument]

    @classmethod
    def setup_class(cls) -> None:
        cls.source = WORKFLOW.read_text()
        cls.workflow = cast("WorkflowDocument", yaml.safe_load(cls.source))

    def test_main_checks_are_individual_jobs(self) -> None:
        assert "matrix:" not in self.source
        assert "${{ matrix." not in self.source
        assert set(self.workflow["jobs"]) == {
            "fmt-check",
            "lint",
            "docs-links",
            "type",
            "type-casts",
            "analyze",
            "test-fast",
            "test-medium",
            "test-slow",
            "build",
            "coverage",
            "audit",
            "mutation-full-frontend",
            "mutation-full-backend",
            "mutation-full-report",
        }

    def test_main_checks_form_expected_graph(self) -> None:
        jobs = self.workflow["jobs"]
        expected = {
            "lint": "fmt-check",
            "docs-links": "fmt-check",
            "type-casts": "lint",
            "type": "type-casts",
            "analyze": "type",
            "test-fast": "analyze",
            "test-medium": "test-fast",
            "test-slow": "test-medium",
            "build": "test-slow",
            "coverage": "build",
            "audit": "coverage",
            "mutation-full-frontend": "audit",
            "mutation-full-backend": "audit",
        }
        for job, dependency in expected.items():
            needs = jobs[job].get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            assert dependency in needs

        assert jobs["lint"]["needs"] == "fmt-check"
        assert jobs["docs-links"]["needs"] == "fmt-check"
        assert jobs["type-casts"]["needs"] == "lint"
        assert jobs["type"]["needs"] == "type-casts"
        assert set(jobs["audit"]["needs"]) == {"coverage", "docs-links"}

    def test_main_jobs_request_specific_python_profiles(self) -> None:
        """Keep main jobs on the same minimal dependency profiles as PR jobs."""
        expected = {
            "fmt-check": "format",
            "lint": "lint",
            "type": "type",
            "type-casts": "ci",
            "analyze": "analyze",
            "test-fast": "test",
            "test-medium": "test",
            "test-slow": "test",
            "coverage": "coverage",
            "audit": "audit",
            "mutation-full-backend": "mutation",
        }
        for job, profile in expected.items():
            block = re.search(
                rf"^    {job}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            assert block is not None, job
            assert f"python-profile: {profile}" in block.group("body"), job

    def test_full_mutation_sweep_runs_in_parallel_with_reusable_caches(self) -> None:
        jobs = self.workflow["jobs"]

        for job in ("mutation-full-frontend", "mutation-full-backend"):
            assert jobs[job].get("needs") == "audit"

        frontend = re.search(
            r"^    mutation-full-frontend:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        backend = re.search(
            r"^    mutation-full-backend:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert frontend is not None
        assert backend is not None
        assert "path: web/reports/stryker-incremental.json" in frontend.group("body")
        assert "hashFiles('web/package-lock.json')" in frontend.group("body")
        assert "hashFiles('web/stryker.conf.ts')" in frontend.group("body")
        assert "${{ github.sha }}" in frontend.group("body")
        assert "restore-keys:" in frontend.group("body")
        assert "uses: actions/cache/restore@v6" in frontend.group("body")
        assert "id: restore-stryker" in frontend.group("body")
        assert "uses: actions/cache/save@v6" in frontend.group("body")
        assert "steps.restore-stryker.outputs.cache-hit != 'true'" in frontend.group("body")
        assert "run: make m-front" in frontend.group("body")
        assert "path: mutants" in backend.group("body")
        assert "hashFiles('uv.lock')" in backend.group("body")
        assert "hashFiles('pyproject.toml')" in backend.group("body")
        assert "${{ github.sha }}" in backend.group("body")
        assert "restore-keys:" in backend.group("body")
        assert "uses: actions/cache/restore@v6" in backend.group("body")
        assert "id: restore-mutmut" in backend.group("body")
        assert "uses: actions/cache/save@v6" in backend.group("body")
        assert "steps.restore-mutmut.outputs.cache-hit != 'true'" in backend.group("body")
        assert "run: make m-back" in backend.group("body")

        report_needs = jobs["mutation-full-report"].get("needs")
        assert isinstance(report_needs, list)
        assert set(report_needs) == {
            "mutation-full-frontend",
            "mutation-full-backend",
        }
        report = self.workflow["jobs"]["mutation-full-report"]
        assert report["if"] == (
            "always() && github.event_name == 'schedule' && "
            "(needs.mutation-full-frontend.result == 'failure' || "
            "needs.mutation-full-backend.result == 'failure')"
        )
        assert report["permissions"] == {"issues": "write"}
        report_source = re.search(
            r"^    mutation-full-report:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert report_source is not None
        assert "uses: actions/github-script@v9" in report_source.group("body")
        assert "FRONTEND_RESULT:" in report_source.group("body")
        assert "BACKEND_RESULT:" in report_source.group("body")
        assert "github.paginate" in report_source.group("body")
        assert "!issue.pull_request" in report_source.group("body")

    def test_main_coverage_publishes_the_trusted_baseline(self) -> None:
        block = re.search(
            r"^    coverage:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        assert "run: make coverage-baseline" in block.group("body")
        assert "uses: actions/cache/save@v6" in block.group("body")
        assert "key: coverage-baseline-v1-${{ github.sha }}" in block.group("body")

    def test_deploy_bounds_docker_storage_before_fetch(self) -> None:
        source = DEPLOY_WORKFLOW.read_text()
        build_cache_gc = "docker buildx prune -af --max-used-space 4gb --min-free-space 8gb"
        image_gc = 'docker image prune -af --filter "until=48h"'
        container_gc = 'docker container prune -f --filter "until=48h"'

        assert source.count(build_cache_gc) == 1
        assert source.count(image_gc) == 1
        assert source.count(container_gc) == 1
        assert source.index(build_cache_gc) < source.index("git fetch origin main")
        assert "free_bytes" in source
        assert "5368709120" in source

    def test_production_host_bounds_docker_storage(self) -> None:
        compose = yaml.safe_load(PRODUCTION_COMPOSE.read_text())
        expected_logging = {
            "driver": "local",
            "options": {"max-size": "20m", "max-file": "3"},
        }
        for service in ("monori", "back", "sync"):
            assert compose["services"][service]["logging"] == expected_logging

        assert compose["services"]["monori"]["depends_on"] == {
            "back": {"condition": "service_healthy"}
        }
        assert compose["services"]["back"]["depends_on"] == {
            "sync": {"condition": "service_healthy"}
        }
        assert "openapi.json" in compose["services"]["back"]["healthcheck"]["test"][-1]
        assert "/health" in compose["services"]["sync"]["healthcheck"]["test"][-1]

        assert json.loads(DOCKER_DAEMON_CONFIG.read_text()) == {
            "log-driver": "local",
            "log-opts": {"max-size": "20m", "max-file": "3"},
        }
        gc_service = DOCKER_GC_SERVICE.read_text()
        assert "--max-used-space 4gb --min-free-space 8gb" in gc_service
        assert "image prune -af --filter until=48h" in gc_service
        assert "container prune -f --filter until=48h" in gc_service
        assert "OnCalendar=*-*-* 03:30:00" in DOCKER_GC_TIMER.read_text()
