# Copyright (c) 2026
from pathlib import Path

import yaml


def test_generated_release_ends_with_one_gitops_commit() -> None:
    root = Path(".github/workflows")
    release = yaml.safe_load((root / "release.yml").read_text())
    assert release["on"] == {"push": {"branches": ["main"]}}
    jobs = release["jobs"]
    assert set(jobs) == {"accept", "build", "publish", "promote"}
    for job, previous in (("build", "accept"), ("publish", "build"), ("promote", "publish")):
        assert jobs[job]["needs"] == [previous]
    actions = [
        step for step in jobs["promote"]["steps"] if "deploy-to-socrat@" in step.get("uses", "")
    ]
    assert len(actions) == 1
    assert set(actions[0]["with"]) == {"images", "token"}
    assert not (root / "publish-image.yml").exists()
