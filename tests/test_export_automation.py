from pathlib import Path

from export_automation import ExportConfig, ExportRecord, PREFERRED_FORMATS, write_manifest


def test_launch_args_include_extension_flags(tmp_path: Path):
    config = ExportConfig(
        job_id="job1",
        target_url="https://example.com",
        extension_path=tmp_path / "extension",
        browser_profile_path=tmp_path / "profile",
    )

    args = config.launch_args

    assert any(arg.startswith("--disable-extensions-except=") for arg in args)
    assert any(arg.startswith("--load-extension=") for arg in args)


def test_format_preference_policy_png_first_then_fallbacks():
    assert PREFERRED_FORMATS == ["png", "jpg", "webp"]


def test_manifest_records_path_format_and_timestamps(tmp_path: Path):
    config = ExportConfig(
        job_id="job2",
        target_url="https://example.com/nlm",
        extension_path=tmp_path / "extension",
        browser_profile_path=tmp_path / "profile",
        out_root=tmp_path / "out",
    )
    record = ExportRecord(file_path="out/job2/infographic/example.png", file_format="png")

    manifest_path = write_manifest(config, [record])

    assert manifest_path.exists()
    data = manifest_path.read_text(encoding="utf-8")
    assert '"job_id": "job2"' in data
    assert '"file_path": "out/job2/infographic/example.png"' in data
    assert '"file_format": "png"' in data
    assert '"exported_at":' in data
