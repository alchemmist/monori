from __future__ import annotations

import base64
import hashlib

from monori.ci.lib.flaky_tests import (
    AttemptResult,
    AttemptStatus,
    CollectedTest,
    Lane,
    RepetitionResult,
    RunnerStack,
)
from monori.ci.quality_graph.checks.flaky_tests import (
    FlakyFinding,
    decode_evidence,
    encode_evidence,
    merge_sticky_findings,
    summary_body,
)

HEAD = "a" * 40
NEXT_HEAD = "b" * 40


def finding(status: AttemptStatus = AttemptStatus.FAILED) -> FlakyFinding:
    test = CollectedTest(
        RunnerStack.PYTEST,
        Lane.FAST,
        "server/tests/test_budget.py",
        11,
        "server/tests/test_budget.py::test_new_budget",
        "test_new_budget",
    )
    attempts = tuple(
        AttemptResult(
            number,
            status if number == 4 else AttemptStatus.PASSED,
            number / 10,
            "boom" if number == 4 else "",
        )
        for number in range(1, 11)
    )
    return FlakyFinding(RepetitionResult(test, attempts), "https://example.test/run/1")


def test_sticky_evidence_round_trips_complete_finding_data() -> None:
    marker = encode_evidence(HEAD, (finding(),))

    head, findings = decode_evidence(marker)

    assert head == HEAD
    assert findings == (finding(),)
    assert "monori-qg-sticky: flaky-tests" in marker


def test_sticky_evidence_uses_canonical_compact_json() -> None:
    marker = encode_evidence(HEAD, (finding(),))
    encoded = marker.removeprefix(f"<!-- monori-qg-sticky: flaky-tests {HEAD} ").removesuffix(
        " -->"
    )
    payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()

    assert payload.startswith('[{"attempts":')
    assert " " not in payload


def test_green_rerun_keeps_evidence_on_same_head_and_new_head_clears_it() -> None:
    body = encode_evidence(HEAD, (finding(),))

    assert merge_sticky_findings(body, HEAD, ()) == (finding(),)
    assert merge_sticky_findings(body, NEXT_HEAD, ()) == ()


def test_summary_exposes_attempts_annotations_and_admin_controls() -> None:
    report = summary_body((finding(),), set(), "https://github.com/example/repo/pull/1")

    assert "10" in report.summary
    assert "Attempt 4" in report.summary
    assert "failed" in report.summary
    assert "test_new_budget" in report.summary
    assert report.controls[0].command.startswith("/qg ignore flaky-")
    assert any(control.command == "/qg ignore flaky-tests" for control in report.controls)
    assert any(
        control.command == "/qg ignore-file server/tests/test_budget.py"
        for control in report.controls
    )
    assert hashlib.sha256(report.summary.encode()).hexdigest() == (
        "c33a2c37a93cf220052e7b5b9e8a2ff579a8201ec98e0101a5291238ef4430cc"
    )


def test_empty_summary_explicitly_reports_no_new_product_tests() -> None:
    report = summary_body((), set(), "")

    assert "No newly added frontend or backend tests." in report.summary


def test_malformed_sticky_evidence_is_treated_as_absent() -> None:
    encoded = base64.urlsafe_b64encode(b"[{}]").decode().rstrip("=")
    marker = f"<!-- monori-qg-sticky: flaky-tests {HEAD} {encoded} -->"

    assert decode_evidence(marker) == (None, ())
