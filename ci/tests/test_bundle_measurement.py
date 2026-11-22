# Copyright (c) 2026
import gzip
import json
import sys
import tempfile
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


class TestBundleSize:
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


@pytest.mark.parametrize(
    ("delta", "percent", "expected"),
    [
        (-1, 10.0, "none"),
        (0, 10.0, "none"),
        (3071, 0.299, "none"),
        (3072, 0.299, "info"),
        (1, 0.3, "info"),
        (100, 1.5, "info"),
        (100, 1.501, "significant"),
        (100, 4.0, "significant"),
        (100, 4.001, "critical"),
    ],
)
def test_tier_boundaries(delta: int, percent: float, expected: str) -> None:
    assert tier(delta, percent) == expected


def test_snapshot_filters_and_measures_nested_assets(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    (assets / "nested").mkdir(parents=True)
    payload = b"console.log('hello');" * 20
    (assets / "nested" / "app-12345678.js").write_bytes(payload)
    (assets / "style.css").write_text("body{}")
    (assets / "skip.js.map").write_text("ignored")
    (assets / "skip.JS").write_text("ignored")
    (tmp_path / "outside.js").write_text("ignored")
    (tmp_path / "index.html").write_text(
        '<script src="/assets/nested/app-12345678.js"></script>'
        "<link href='assets/style.css'>"
        '<script src="assets/missing.js"></script>'
        '<script src="outside.js"></script>'
    )
    assert snapshot(tmp_path) == {
        "assets": {
            "assets/nested/app-12345678.js": {
                "size": len(payload),
                "gzip": len(gzip.compress(payload, mtime=0)),
            },
            "assets/style.css": {"size": 6, "gzip": len(gzip.compress(b"body{}", mtime=0))},
        },
        "initial": ["assets/nested/app-12345678.js", "assets/style.css"],
    }


def test_normalized_asset_only_removes_hash_before_extension() -> None:
    assert normalized_asset("assets/foo-short.js") == "assets/foo-short.js"
    assert normalized_asset("assets/foo-Ab_123-xy.css") == "assets/foo.css"
    assert normalized_asset("assets/foo-abcdefgh/bar.js") == "assets/foo-abcdefgh/bar.js"


def test_compare_metrics_and_sorted_growth() -> None:
    base: Snapshot = {
        "initial": ["assets/main-12345678.js", "missing.js"],
        "assets": {
            "assets/main-12345678.js": {"size": 1, "gzip": 100_000},
            "assets/lazy.js": {"size": 1, "gzip": 100_000},
            "assets/gone.js": {"size": 1, "gzip": 100},
        },
    }
    current: Snapshot = {
        "initial": ["assets/main-abcdefgh.js", "missing.js"],
        "assets": {
            "assets/main-abcdefgh.js": {"size": 2, "gzip": 101_000},
            "assets/lazy.js": {"size": 2, "gzip": 110_000},
            "assets/new.css": {"size": 2, "gzip": 500},
        },
    }
    result = compare(base, current)
    assert result == {
        "entries": [
            {
                "id": "bundle-initial-load",
                "label": "Initial load (gzip)",
                "base": 100_000,
                "current": 101_000,
                "delta": 1_000,
                "percent": 1.0,
                "tier": "info",
            },
            {
                "id": "bundle-total-assets",
                "label": "Total assets (gzip)",
                "base": 200_100,
                "current": 211_500,
                "delta": 11_400,
                "percent": 11_400 / 200_100 * 100,
                "tier": "critical",
            },
        ],
        "assetGrowth": [
            {"asset": "assets/lazy.js", "base": 100_000, "current": 110_000, "delta": 10_000},
            {"asset": "assets/main.js", "base": 100_000, "current": 101_000, "delta": 1_000},
            {"asset": "assets/new.css", "base": 0, "current": 500, "delta": 500},
        ],
        "verdict": "critical",
    }


def test_compare_zero_base_shrink_and_growth_limit() -> None:
    empty: Snapshot = {"assets": {}, "initial": []}
    result = compare(empty, empty)
    entries = cast("list[dict[str, object]]", result["entries"])
    assert [(entry["percent"], entry["tier"]) for entry in entries] == [(0.0, "none")] * 2
    current: Snapshot = {
        "assets": {f"assets/{i}.js": {"size": 0, "gzip": i} for i in range(1, 13)},
        "initial": ["assets/1.js"],
    }
    result = compare(empty, current)
    entries = cast("list[dict[str, object]]", result["entries"])
    assert [(entry["percent"], entry["tier"]) for entry in entries] == [(100.0, "critical")] * 2
    growth = cast("list[dict[str, object]]", result["assetGrowth"])
    assert [item["delta"] for item in growth] == list(range(12, 2, -1))
    shrunk = compare(current, empty)
    assert shrunk["verdict"] == "none"
    assert shrunk["assetGrowth"] == []
    entries = cast("list[dict[str, object]]", shrunk["entries"])
    assert [(entry["delta"], entry["percent"]) for entry in entries] == [
        (-1, -100.0),
        (-78, -100.0),
    ]


def test_compare_cli_noncritical_exit_and_complete_output(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    current = tmp_path / "current.json"
    output = tmp_path / "report.json"
    data: Snapshot = {"initial": [], "assets": {}}
    base.write_text(json.dumps(data))
    current.write_text(json.dumps(data))
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
            "42",
            "--head-sha",
            "abc",
        ]
    ):
        assert main() == 0
    expected = compare(data, data)
    expected.update({"prNumber": 42, "headSha": "abc"})
    assert output.read_text() == json.dumps(expected, indent=2, sort_keys=True) + "\n"
