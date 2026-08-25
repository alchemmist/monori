import sys
from types import SimpleNamespace

import pytest

from monori.ci.quality_graph.checks import flaky_runner


@pytest.mark.parametrize("expected", [0, 1])
def test_main_returns_the_flaky_test_verdict(
    monkeypatch: pytest.MonkeyPatch, expected: int
) -> None:
    unstable = expected == 1
    monkeypatch.setattr(
        flaky_runner,
        "execute_manifest",
        lambda _: (SimpleNamespace(unstable=unstable),),
    )
    monkeypatch.setattr(sys, "argv", ["flaky-runner", "--manifest", "manifest.json"])

    assert flaky_runner.main() == expected
