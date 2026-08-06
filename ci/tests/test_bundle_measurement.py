import json
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict, cast

import pytest

from monori.ci.quality_graph.checks.bundle_measurement import (
    Snapshot,
    compare,
    main,
    normalized_asset,
    snapshot,
    tier,
)
from monori.ci.quality_graph.checks.bundle_size import format_kib


class BundleEntry(TypedDict):
    id: str


class AssetGrowth(TypedDict):
    delta: int


@contextmanager
def arguments(values: list[str]) -> Iterator[None]:
    """Temporarily replace command-line arguments."""
    previous = sys.argv
    sys.argv = values
    try:
        yield
    finally:
        sys.argv = previous


class BundleSizeTest(unittest.TestCase):
    def test_hashes_are_removed_for_asset_comparison(self) -> None:
        assert normalized_asset("assets/index-AbCdEf12.js") == "assets/index.js"

    def test_noise_floor_requires_both_limits_to_be_exceeded(self) -> None:
        assert tier(2 * 1024, 1.0) == "info"
        assert tier(1024, 0.2) == "none"

    def test_critical_metric_and_asset_growth(self) -> None:
        base = {
            "initial": ["assets/index-12345678.js"],
            "assets": {"assets/index-12345678.js": {"size": 100, "gzip": 100_000}},
        }
        current = {
            "initial": ["assets/index-abcdefgh.js"],
            "assets": {"assets/index-abcdefgh.js": {"size": 110, "gzip": 110_000}},
        }
        result = compare(cast("Snapshot", base), cast("Snapshot", current))
        assert result["verdict"] == "critical"
        entries = cast("list[BundleEntry]", result["entries"])
        growth = cast("list[AssetGrowth]", result["assetGrowth"])
        assert entries[0]["id"] == "bundle-initial-load"
        assert growth[0]["delta"] == 10_000

    def test_format_kib_rejects_boolean_values(self) -> None:
        with pytest.raises(TypeError, match="numeric bundle size"):
            format_kib(value=True)

    def test_snapshot_and_cli_measure_real_build_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = root / "dist"
            assets = dist / "assets"
            assets.mkdir(parents=True)
            (assets / "index-12345678.js").write_text("console.log('bundle')")
            (assets / "styles-12345678.css").write_text("body { color: red; }")
            (assets / "ignored.txt").write_text("ignored")
            (dist / "index.html").write_text(
                '<script src="/assets/index-12345678.js"></script>'
                '<link href="assets/styles-12345678.css">'
            )

            measured = snapshot(dist)
            assert measured["initial"] == [
                "assets/index-12345678.js",
                "assets/styles-12345678.css",
            ]
            output = root / "snapshot.json"
            with arguments(["bundle", "measure", "--dist", str(dist), "--output", str(output)]):
                assert main() == 0
            assert json.loads(output.read_text())["initial"] == measured["initial"]

    def test_compare_cli_writes_metadata_and_returns_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.json"
            current = root / "current.json"
            output = root / "report.json"
            base.write_text(json.dumps({"initial": ["assets/a.js"], "assets": {}}))
            current.write_text(
                json.dumps(
                    {
                        "initial": ["assets/a.js"],
                        "assets": {"assets/a.js": {"size": 10_000, "gzip": 10_000}},
                    }
                )
            )
            with arguments(
                [
                    "bundle",
                    "compare",
                    "--base",
                    str(base),
                    "--current",
                    str(current),
                    "--output",
                    str(output),
                    "--pr-number",
                    "7",
                    "--head-sha",
                    "head-sha",
                ]
            ):
                assert main() == 1
            report = json.loads(output.read_text())
            assert report["prNumber"] == 7
            assert report["headSha"] == "head-sha"


if __name__ == "__main__":
    unittest.main()
