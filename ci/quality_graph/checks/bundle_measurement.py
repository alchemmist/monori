"""Measure and compare gzip sizes of the frontend build."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path
from typing import TypedDict, cast

NOISE_PERCENT = 0.3
NOISE_BYTES = 3 * 1024
INFO_PERCENT = 1.5
SIGNIFICANT_PERCENT = 4.0
ASSET_HASH_RE = re.compile(r"-[A-Za-z0-9_-]{8,}(?=\.)")
ASSET_RE = re.compile(r"(?:src|href)=['\"](?:/)?(assets/[^'\"]+\.(?:js|css))['\"]")

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class Asset(TypedDict):
    """Single asset snapshot entry with raw and gzipped sizes."""

    size: int
    gzip: int


class Snapshot(TypedDict):
    """Parsed frontend bundle snapshot."""

    assets: dict[str, Asset]
    initial: list[str]


class AssetGrowth(TypedDict):
    """Growth entry describing regression details for a single asset."""

    asset: str
    base: int
    current: int
    delta: int


def gzip_size(path: Path) -> int:
    """Gzip size for this module."""
    return len(gzip.compress(path.read_bytes(), mtime=0))


def snapshot(dist: Path) -> Snapshot:
    """Snapshot for this module."""
    assets: dict[str, Asset] = {}
    assets_dir = dist / "assets"
    for path in sorted(assets_dir.rglob("*")):
        if path.is_file() and path.suffix in {".js", ".css"}:
            relative = path.relative_to(dist).as_posix()
            assets[relative] = {"size": path.stat().st_size, "gzip": gzip_size(path)}

    html = (dist / "index.html").read_text()
    initial = [asset for asset in ASSET_RE.findall(html) if asset in assets]
    return {"assets": assets, "initial": initial}


def normalized_asset(path: str) -> str:
    """Normalize an asset path by removing the build hash."""
    return ASSET_HASH_RE.sub("", path)


def tier(delta: int, percent: float) -> str:
    """Tier for this module."""
    if delta <= 0 or (percent < NOISE_PERCENT and delta < NOISE_BYTES):
        return "none"
    if percent <= INFO_PERCENT:
        return "info"
    if percent <= SIGNIFICANT_PERCENT:
        return "significant"
    return "critical"


def compare(base: Snapshot, current: Snapshot) -> dict[str, JsonValue]:
    """Compare for this module."""

    def total(names: list[str]) -> int:
        return sum(current["assets"].get(name, {"gzip": 0})["gzip"] for name in names)

    def metric(
        metric_id: str, label: str, base_bytes: int, current_bytes: int
    ) -> dict[str, JsonValue]:
        delta = current_bytes - base_bytes
        percent = (delta / base_bytes * 100) if base_bytes else (100.0 if delta else 0.0)
        return {
            "id": f"bundle-{metric_id}",
            "label": label,
            "base": base_bytes,
            "current": current_bytes,
            "delta": delta,
            "percent": percent,
            "tier": tier(delta, percent),
        }

    initial_base = sum(base["assets"].get(name, {"gzip": 0})["gzip"] for name in base["initial"])
    initial_current = total(current["initial"])
    total_base = sum(asset["gzip"] for asset in base["assets"].values())
    total_current = sum(asset["gzip"] for asset in current["assets"].values())
    entries = [
        metric("initial-load", "Initial load (gzip)", initial_base, initial_current),
        metric("total-assets", "Total assets (gzip)", total_base, total_current),
    ]

    base_assets = {normalized_asset(name): asset["gzip"] for name, asset in base["assets"].items()}
    current_assets = {
        normalized_asset(name): asset["gzip"] for name, asset in current["assets"].items()
    }
    growth: list[AssetGrowth] = [
        {
            "asset": name,
            "base": base_assets.get(name, 0),
            "current": current_assets[name],
            "delta": current_assets[name] - base_assets.get(name, 0),
        }
        for name in current_assets
        if current_assets[name] > base_assets.get(name, 0)
    ]
    growth.sort(key=lambda item: int(item["delta"]), reverse=True)
    verdict = max(
        (str(entry["tier"]) for entry in entries),
        key=("none", "info", "significant", "critical").index,
    )
    return {
        "entries": cast("JsonValue", entries),
        "assetGrowth": cast("JsonValue", growth[:10]),
        "verdict": verdict,
    }


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    measure_parser = subparsers.add_parser("measure")
    measure_parser.add_argument("--dist", type=Path, required=True)
    measure_parser.add_argument("--output", type=Path, required=True)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--base", type=Path, required=True)
    compare_parser.add_argument("--current", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    compare_parser.add_argument("--pr-number", type=int, required=True)
    compare_parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    if args.command == "measure":
        result: JsonValue = cast("JsonValue", snapshot(args.dist))
    else:
        comparison = compare(
            json.loads(args.base.read_text()), json.loads(args.current.read_text())
        )
        comparison["prNumber"] = args.pr_number
        comparison["headSha"] = args.head_sha
        result = comparison
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.command == "compare":
        comparison = cast("dict[str, JsonValue]", result)
        return 1 if comparison["verdict"] == "critical" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
