import unittest
from typing import TypedDict, cast

from ci.quality_graph.checks.bundle_measurement import Snapshot, compare, normalized_asset, tier


class BundleEntry(TypedDict):
    id: str


class AssetGrowth(TypedDict):
    delta: int


class BundleSizeTest(unittest.TestCase):
    def test_hashes_are_removed_for_asset_comparison(self) -> None:
        self.assertEqual(normalized_asset("assets/index-AbCdEf12.js"), "assets/index.js")

    def test_noise_floor_requires_both_limits_to_be_exceeded(self) -> None:
        self.assertEqual(tier(2 * 1024, 1.0), "info")
        self.assertEqual(tier(1024, 0.2), "none")

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
        self.assertEqual(result["verdict"], "critical")
        entries = cast("list[BundleEntry]", result["entries"])
        growth = cast("list[AssetGrowth]", result["assetGrowth"])
        self.assertEqual(entries[0]["id"], "bundle-initial-load")
        self.assertEqual(growth[0]["delta"], 10_000)


if __name__ == "__main__":
    unittest.main()
