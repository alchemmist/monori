import json
import pathlib

from performance import report


def test_report_renders_percentiles_and_verdict(tmp_path: pathlib.Path) -> None:
    payload = {
        "metrics": {
            "http_reqs": {"values": {"count": 120, "rate": 12.5}},
            "http_req_duration": {
                "values": {"med": 10, "p(90)": 20, "p(95)": 30, "p(99)": 40, "max": 50}
            },
            "http_req_failed": {"values": {"rate": 0}},
            "checks": {"values": {"rate": 1}, "thresholds": {"rate>0.995": {"ok": True}}},
            "operation_duration": {
                "values": {"med": 11, "p(90)": 21, "p(95)": 31, "p(99)": 41, "max": 51},
                "thresholds": {"p(95)<300": {"ok": True}},
            },
            "operation_errors": {
                "values": {"rate": 0},
                "thresholds": {"rate<0.005": {"ok": True}},
            },
        }
    }
    source = tmp_path / "DELETE-read-10.json"
    source.write_text(json.dumps(payload))
    result = report.load(source)
    assert result is not None
    assert result.p95 == 31
    assert result.passed
    assert "| DELETE | read | 10 |" in report.render([result])


def test_resource_duration_accepts_compound_container_time() -> None:
    assert report.seconds("1m2.5s") == 62.5
    assert report.seconds("16.5ms") == 0.0165
