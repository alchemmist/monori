import unittest
from typing import override

from ci.quality_graph.checks.frontend_performance import (
    JsonValue,
    apply_command,
    entry_ids,
    finding_id,
)
from ci.quality_graph.commands import parse_command


class FrontendPerformanceGateTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
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
        self.assertEqual(finding_id(self.entries[0]), "frontend-fea774364776")
        self.assertEqual(entry_ids(self.entries), {"frontend-fea774364776"})

    def test_ignore_accepts_only_frontend_ids(self) -> None:
        command = parse_command("/qg ignore frontend-fea774364776,object-abc123")

        self.assertEqual(apply_command(command, self.entries, set()), {"frontend-fea774364776"})

    def test_ignore_all_and_remove_ignore(self) -> None:
        all_command = parse_command("/qg ignore frontend")
        remove_command = parse_command("/qg remove-ignore frontend-fea774364776")

        approved = apply_command(all_command, self.entries, set())
        self.assertEqual(apply_command(remove_command, self.entries, approved), set())


if __name__ == "__main__":
    unittest.main()
