from __future__ import annotations

from typing import TYPE_CHECKING

from monori.ci.quality_graph.checks.frontend_performance import (
    APPROVALS,
    FrontendPerformanceFinding,
    entry_ids,
    finding_id,
)
from monori.ci.quality_graph.commands import parse_command

if TYPE_CHECKING:
    from monori.common import JsonValue


class TestFrontendPerformanceGate:
    def setup_method(self) -> None:
        self.entries: list[dict[str, JsonValue]]
        self.entries = [
            {
                "route_id": "categories",
                "route_label": "Categories",
                "metric_id": "lcp",
                "metric_label": "LCP",
                "tier": "critical",
            },
            {
                "route_id": "login",
                "route_label": "Login",
                "metric_id": "ttfb",
                "metric_label": "TTFB",
                "tier": "none",
            },
        ]

    def test_finding_id_is_namespaced_and_stable(self) -> None:
        assert finding_id(self.entries[0]) == "frontend-fea774364776"
        assert entry_ids(self.entries) == {"frontend-fea774364776"}

    def test_ignore_accepts_only_frontend_ids(self) -> None:
        command = parse_command("/qg ignore frontend-fea774364776,object-abc123")

        assert command is not None
        findings = [FrontendPerformanceFinding("frontend-fea774364776")]
        assert APPROVALS.select_findings(command, findings) == {"frontend-fea774364776"}

    def test_ignore_all_and_remove_ignore(self) -> None:
        all_command = parse_command("/qg ignore frontend")
        remove_command = parse_command("/qg remove-ignore frontend")

        assert all_command is not None
        assert remove_command is not None
        findings = [FrontendPerformanceFinding("frontend-fea774364776")]
        assert APPROVALS.select_findings(all_command, findings) == {"frontend-fea774364776"}
        assert APPROVALS.select_findings(remove_command, findings) == {"frontend-fea774364776"}
