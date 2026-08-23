from monori.ci.lib.comments import comment_body, preserve_comment_state


class TestPullRequestComment:
    def test_comment_body_has_a_stable_report_marker(self) -> None:
        assert (
            comment_body("bundle-size", "## Bundle size\n")
            == "<!-- monori-report: bundle-size -->\n\n## Bundle size\n"
        )

    def test_dashboard_replacement_preserves_bot_owned_sticky_state(self) -> None:
        previous = (
            "<!-- monori-report: quality-graph -->\n"
            "<!-- monori-qg-sticky: flaky-tests head encoded -->\n\n"
            "old dashboard\n"
        )
        rendered = "<!-- monori-report: quality-graph -->\n\nnew dashboard\n"

        assert preserve_comment_state(previous, rendered) == (
            "<!-- monori-report: quality-graph -->\n"
            "<!-- monori-qg-sticky: flaky-tests head encoded -->\n\n"
            "new dashboard\n"
        )

    def test_dashboard_replacement_preserves_each_distinct_sticky_state(self) -> None:
        previous = (
            "<!-- monori-report: quality-graph -->\n"
            "<!-- monori-qg-sticky: flaky-tests first encoded-one -->\n"
            "<!-- monori-qg-sticky: another-check second encoded-two -->\n\n"
            "old dashboard\n"
        )
        rendered = "<!-- monori-report: quality-graph -->\n\nnew dashboard\n"

        assert preserve_comment_state(previous, rendered) == (
            "<!-- monori-report: quality-graph -->\n"
            "<!-- monori-qg-sticky: flaky-tests first encoded-one -->\n"
            "<!-- monori-qg-sticky: another-check second encoded-two -->\n\n"
            "new dashboard\n"
        )
