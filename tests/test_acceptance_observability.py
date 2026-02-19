import json
from pathlib import Path

from nlm_extension.observability import (
    capture_failure_artifacts,
    create_run_logger,
    validate_manifest,
    write_manifest,
)


def _manifest(tmp_path: Path):
    return {
        "input": {"path": "input/notebook.ipynb", "hash": "sha256:abc123"},
        "notebook": {"id": "nb-001", "url": "https://example.com/notebooks/nb-001"},
        "audio_assets": [
            {"id": "intro", "path": "out/job/audio/intro.mp3", "duration_seconds": 3.2}
        ],
        "video": {"share_link": "https://example.com/video/v1", "duration_seconds": 60.0},
        "infographic_assets": [
            {"id": "chart-1", "path": "out/job/infographics/chart-1.png", "width": 1200, "height": 800}
        ],
        "timing": {
            "started_at": "2026-01-01T10:00:00Z",
            "ended_at": "2026-01-01T10:01:00Z",
            "total_duration_seconds": 60.0,
        },
        "diagnostics": {
            "log_path": "out/job/logs/run.log",
            "failure_png_path": "out/job/debug/failure.png",
            "failure_html_path": "out/job/debug/page.html",
        },
    }


def test_at1_manifest_schema_and_writer(tmp_path: Path):
    manifest = _manifest(tmp_path)
    validate_manifest(manifest)
    output = write_manifest(manifest, tmp_path / "manifest.json")
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["input"]["hash"].startswith("sha256:")
    assert written["video"]["share_link"]


def test_at2_structured_logging(tmp_path: Path):
    logger, log_path = create_run_logger("job-123", out_root=tmp_path)
    logger.info("pipeline started")

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["message"] == "pipeline started"
    assert record["level"] == "INFO"


class _PageStub:
    def screenshot(self):
        return b"png-bytes"

    def content(self):
        return "<html><body>debug</body></html>"


class _BrokenPageStub:
    def screenshot(self):
        raise RuntimeError("no browser")

    def content(self):
        raise RuntimeError("no html")


def test_at3_failure_handler_emits_artifacts_with_stub(tmp_path: Path):
    artifacts = capture_failure_artifacts("job-789", out_root=tmp_path, page=_PageStub())

    assert artifacts["failure_png_path"].exists()
    assert artifacts["failure_html_path"].exists()
    assert artifacts["failure_png_path"].read_bytes() == b"png-bytes"


def test_at4_failure_handler_fallback_when_external_dependency_unavailable(tmp_path: Path):
    artifacts = capture_failure_artifacts("job-987", out_root=tmp_path, page=_BrokenPageStub())

    assert artifacts["failure_png_path"].exists()
    assert artifacts["failure_html_path"].exists()
    assert "failure capture unavailable" in artifacts["failure_html_path"].read_text(encoding="utf-8")


def test_at5_example_manifest_fixture_structure():
    fixture_path = Path(__file__).parent / "fixtures" / "example_manifest.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    validate_manifest(fixture)
    assert fixture["notebook"]["id"] == "nb-demo-001"
