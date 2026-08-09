import contextlib
import json
import os
import tempfile
from pathlib import Path

import pytest
from dulwich import porcelain
from dulwich.repo import Repo

from monori.ci.lib import mutation_diff_gate as module


class TestMutationDiffGate:
    def test_parses_mutmut_function_names(self) -> None:
        assert module.mutant_function("app.foo.x_run__mutmut_1") == ("run", None)
        assert module.mutant_function("app.foo.ǁAccountǁx_save__mutmut_2") == (
            "save",
            "Account",
        )

    def test_maps_mutant_metadata_to_its_configured_source_path(self) -> None:
        assert (
            module.source_path_for_mutant(Path("monori/server/app/example.py.meta"))
            == "server/app/example.py"
        )
        assert (
            module.source_path_for_mutant(Path("monori/ci/quality_graph/app/example.py.meta"))
            == "ci/quality_graph/app/example.py"
        )
        assert (
            module.source_path_for_mutant(Path("monori/ci/lib/comments.py.meta"))
            == "ci/lib/comments.py"
        )

    def test_collects_changed_functions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "server/app/example.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "class Account:\n"
                "    def save(self):\n"
                "        return True\n"
                "\n"
                "def untouched():\n"
                "    return False\n"
            )

            result = module.changed_functions(root, {"server/app/example.py": {3}})

        assert result == {"server/app/example.py": {("save", "Account")}}

    def test_maps_deletion_only_hunks_to_changed_lines(self) -> None:
        diff = """\
diff --git a/server/app/example.py b/server/app/example.py
--- a/server/app/example.py
+++ b/server/app/example.py
@@ -5 +4,0 @@
-    removed = True
"""

        assert module.parse_changed_lines(diff) == {"server/app/example.py": {4}}

    def test_ignores_deleted_file_before_modified_file(self) -> None:
        diff = """\
diff --git a/server/app/deleted.py b/server/app/deleted.py
--- a/server/app/deleted.py
+++ /dev/null
@@ -1 +0,0 @@
-removed = True
diff --git a/server/app/example.py b/server/app/example.py
--- a/server/app/example.py
+++ b/server/app/example.py
@@ -3 +3 @@
-old = True
\\ No newline at end of file
+new = True
\\ No newline at end of file
"""

        assert module.parse_changed_lines(diff) == {"server/app/example.py": {2, 3}}

    def test_load_meta_reports_missing_statuses(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".meta") as metadata:
            metadata.write("{}")
            metadata.flush()

            with pytest.raises(TypeError, match="missing exit_code_by_key"):
                module.load_meta(Path(metadata.name))

    def test_record_mutant_classifies_every_gate_status(self) -> None:
        stats = module.MutationStats()
        module.record_mutant(stats, "new-survivor", module.SURVIVED, {})
        module.record_mutant(stats, "known-survivor", module.SURVIVED, {"known-survivor": 0})
        module.record_mutant(stats, "killed", 1, {})
        module.record_mutant(stats, "timeout", 24, {})
        module.record_mutant(stats, "uncovered", None, {})
        module.record_mutant(stats, "ignored", 999, {})

        assert stats.killed == 1
        assert stats.survived == 2
        assert stats.other == 2
        assert stats.new_survivors == 1
        assert stats.considered == 5
        assert stats.survivor_keys == ["new-survivor", "known-survivor"]
        assert stats.no_coverage_keys == ["uncovered"]

    def test_collects_relevant_mutation_metadata_and_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mutants = root / "mutants"
            baseline = root / "baseline"
            current_meta = mutants / "monori/server/app/example.py.meta"
            baseline_meta = baseline / "monori/server/app/example.py.meta"
            current_meta.parent.mkdir(parents=True)
            baseline_meta.parent.mkdir(parents=True)
            current_meta.write_text(
                json.dumps(
                    {
                        "exit_code_by_key": {
                            "monori.server.app.example.x_changed__mutmut_1": 0,
                            "monori.server.app.example.x_untouched__mutmut_2": 1,
                        }
                    }
                )
            )
            baseline_meta.write_text(
                json.dumps(
                    {"exit_code_by_key": {"monori.server.app.example.x_changed__mutmut_1": 1}}
                )
            )
            unrelated = mutants / "unknown/example.py.meta"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text(json.dumps({"exit_code_by_key": {}}))
            source = root / "server/app/example.py"
            source.parent.mkdir(parents=True)
            source.write_text("def changed():\n    return True\n")
            request = module.GateRequest(
                mutants_dir=mutants,
                baseline_dir=baseline,
                root=root,
                base="main",
                threshold=90,
                skip_new_survivors=False,
            )

            stats = module.collect_mutation_stats(
                request,
                {"server/app/example.py": {("changed", None)}},
            )

        assert stats.survived == 1
        assert stats.new_survivors == 1
        assert stats.source_findings == [
            (
                "server/app/example.py",
                1,
                "Surviving mutant: monori.server.app.example.x_changed__mutmut_1",
            )
        ]

    def test_verdict_and_empty_results_write_step_summaries(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            previous = os.environ.get("MUTATION_SUMMARY_PATH")
            os.environ["MUTATION_SUMMARY_PATH"] = str(summary)
            try:
                request = module.GateRequest(
                    mutants_dir=Path(),
                    baseline_dir=Path(),
                    root=Path(),
                    base="main",
                    threshold=80,
                    skip_new_survivors=False,
                )
                passing = module.MutationStats(killed=9, survived=1)
                failing = module.MutationStats(
                    killed=1,
                    survived=1,
                    new_survivors=1,
                    survivor_keys=["survivor"],
                    no_coverage_keys=["uncovered"],
                    source_findings=[("server/a:b,c.py", 2, "Surviving mutant")],
                )
                assert module.report_verdict(request, passing) == 0
                assert module.report_verdict(request, failing) == 1
                assert module.append_empty_summary("no changed functions") == 0
            finally:
                if previous is None:
                    os.environ.pop("MUTATION_SUMMARY_PATH", None)
                else:
                    os.environ["MUTATION_SUMMARY_PATH"] = previous

            content = summary.read_text()
            assert "✅ PASS" in content
            assert "❌ FAIL" in content
            assert "Surviving mutants" in content
            assert "Mutants without coverage" in content
            assert "No changed functions" in content
            assert "::error file=server/a%3Ab%2Cc.py,line=2" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("stats", "skip_new_survivors", "expected"),
        [
            (module.MutationStats(killed=9, survived=1), False, 0),
            (
                module.MutationStats(killed=9, survived=1, new_survivors=1),
                False,
                1,
            ),
            (
                module.MutationStats(killed=9, survived=1, new_survivors=1),
                True,
                0,
            ),
            (module.MutationStats(killed=7, survived=3), False, 1),
        ],
    )
    def test_verdict_enforces_score_and_new_survivors_independently(
        self,
        tmp_path: Path,
        stats: module.MutationStats,
        *,
        skip_new_survivors: bool,
        expected: int,
    ) -> None:
        """Keep the score threshold and survivor regression policy independent."""
        summary = tmp_path / "summary.md"
        previous = os.environ.get("MUTATION_SUMMARY_PATH")
        os.environ["MUTATION_SUMMARY_PATH"] = str(summary)
        try:
            result = module.report_verdict(
                module.GateRequest(
                    Path(),
                    Path(),
                    Path(),
                    "main",
                    80,
                    skip_new_survivors,
                ),
                stats,
            )
        finally:
            if previous is None:
                os.environ.pop("MUTATION_SUMMARY_PATH", None)
            else:
                os.environ["MUTATION_SUMMARY_PATH"] = previous

        assert result == expected
        expected_status = "✅ PASS" if expected == 0 else "❌ FAIL"
        score = 100 * stats.killed / stats.considered
        assert summary.read_text() == (
            "## Python mutation diff\n\n"
            "| Metric | Value |\n"
            "| --- | ---: |\n"
            f"| Status | {expected_status} |\n"
            f"| Killed | {stats.killed} |\n"
            f"| Survived | {stats.survived} |\n"
            "| No coverage | 0 |\n"
            f"| New survivors | {stats.new_survivors} |\n"
            f"| Considered | {stats.considered} |\n"
            f"| Score | {score:.2f}% |\n"
            "| Threshold | 80% |\n"
        )

    def test_revision_resolution_rejects_unknown_reference(self, tmp_path: Path) -> None:
        repository = Repo.init(tmp_path)
        source = tmp_path / "example.py"
        source.write_text("value = 1\n")
        porcelain.add(repository, paths=["example.py"])
        porcelain.commit(
            repository,
            message=b"initial",
            author=b"Test <test@example.com>",
            committer=b"Test <test@example.com>",
        )
        assert module.commit_for_revision(repository, "HEAD").id
        with pytest.raises(RuntimeError, match="Cannot resolve git revision"):
            module.commit_for_revision(repository, "missing-revision")

    def test_reads_changed_lines_from_a_real_repository(self, tmp_path: Path) -> None:
        repository = Repo.init(tmp_path)
        source = tmp_path / "server/app/example.py"
        source.parent.mkdir(parents=True)
        source.write_text("def value():\n    return 1\n")
        porcelain.add(repository, paths=["server/app/example.py"])
        base = porcelain.commit(
            repository,
            message=b"base",
            author=b"Test <test@example.com>",
            committer=b"Test <test@example.com>",
        )
        source.write_text("def value():\n    return 2\n")
        ignored = tmp_path / "docs/example.py"
        ignored.parent.mkdir()
        ignored.write_text("value = 2\n")
        porcelain.add(repository, paths=["server/app/example.py", "docs/example.py"])
        porcelain.commit(
            repository,
            message=b"head",
            author=b"Test <test@example.com>",
            committer=b"Test <test@example.com>",
        )

        with contextlib.chdir(tmp_path):
            lines = module.changed_lines(base.decode())

        assert lines == {"server/app/example.py": {1, 2}}

    def test_gate_scores_real_git_diff_and_mutant_metadata(self, tmp_path: Path) -> None:
        repository = Repo.init(tmp_path)
        source = tmp_path / "server/app/example.py"
        source.parent.mkdir(parents=True)
        source.write_text("def value():\n    return 1\n")
        porcelain.add(repository, paths=["server/app/example.py"])
        base = porcelain.commit(
            repository,
            message=b"base",
            author=b"Test <test@example.com>",
            committer=b"Test <test@example.com>",
        )
        source.write_text("def value():\n    return 2\n")
        porcelain.add(repository, paths=["server/app/example.py"])
        porcelain.commit(
            repository,
            message=b"head",
            author=b"Test <test@example.com>",
            committer=b"Test <test@example.com>",
        )
        mutants = tmp_path / "mutants"
        metadata = mutants / "monori/server/app/example.py.meta"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(
            json.dumps({"exit_code_by_key": {"monori.server.app.example.x_value__mutmut_1": 1}})
        )
        summary = tmp_path / "summary.md"
        previous = os.environ.get("MUTATION_SUMMARY_PATH")
        os.environ["MUTATION_SUMMARY_PATH"] = str(summary)
        try:
            with contextlib.chdir(tmp_path):
                result = module.gate_python(
                    module.GateRequest(
                        mutants_dir=mutants,
                        baseline_dir=tmp_path / "baseline",
                        root=tmp_path,
                        base=base.decode(),
                        threshold=90,
                        skip_new_survivors=False,
                    )
                )
        finally:
            if previous is None:
                os.environ.pop("MUTATION_SUMMARY_PATH", None)
            else:
                os.environ["MUTATION_SUMMARY_PATH"] = previous

        assert result == 0
        assert "100.00%" in summary.read_text()
