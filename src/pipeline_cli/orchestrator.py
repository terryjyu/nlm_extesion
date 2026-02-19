from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ExitCode, PipelineError
from .job import JobPaths


@dataclass(frozen=True)
class RunConfig:
    pdf: Path
    notebook_name: str
    headful: bool


def run_pipeline(config: RunConfig, job_paths: JobPaths) -> dict[str, Any]:
    phase_results: list[dict[str, Any]] = []

    for phase_name, phase in (
        ("notebook ingest", _phase_notebook_ingest),
        ("audio generation", _phase_audio_generation),
        ("video generation", _phase_video_generation),
        ("infographic export", _phase_infographic_export),
    ):
        try:
            result = phase(config, job_paths)
            phase_results.append({"phase": phase_name, "status": "ok", "result": result})
        except Exception as exc:  # pragma: no cover
            raise PipelineError(
                code=ExitCode.PHASE_FAILED,
                message=f"Phase failed: {phase_name}",
                details={"phase": phase_name, "reason": str(exc)},
            ) from exc

    manifest = {
        "ok": True,
        "job_id": job_paths.job_id,
        "pdf": str(config.pdf),
        "notebook_name": config.notebook_name,
        "headful": config.headful,
        "outputs": {
            "base": str(job_paths.base),
            "audio": str(job_paths.audio),
            "video": str(job_paths.video),
            "infographic": str(job_paths.infographic),
            "debug": str(job_paths.debug),
        },
        "phases": phase_results,
    }
    _write_manifest(job_paths, manifest)
    return manifest


def _phase_notebook_ingest(config: RunConfig, job_paths: JobPaths) -> dict[str, Any]:
    ingest_info = {
        "source_pdf": str(config.pdf),
        "notebook_name": config.notebook_name,
        "mode": "headful" if config.headful else "headless",
    }
    _write_json(job_paths.debug / "01_notebook_ingest.json", ingest_info)
    return ingest_info


def _phase_audio_generation(config: RunConfig, job_paths: JobPaths) -> dict[str, Any]:
    audio_file = job_paths.audio / "narration.txt"
    audio_file.write_text(f"Audio placeholder for {config.pdf.name}\n", encoding="utf-8")
    return {"artifact": str(audio_file)}


def _phase_video_generation(config: RunConfig, job_paths: JobPaths) -> dict[str, Any]:
    video_file = job_paths.video / "storyboard.txt"
    video_file.write_text(f"Video placeholder for {config.pdf.name}\n", encoding="utf-8")
    return {"artifact": str(video_file)}


def _phase_infographic_export(config: RunConfig, job_paths: JobPaths) -> dict[str, Any]:
    infographic_file = job_paths.infographic / "infographic.txt"
    infographic_file.write_text(f"Infographic placeholder for {config.pdf.name}\n", encoding="utf-8")
    return {"artifact": str(infographic_file)}


def _write_manifest(job_paths: JobPaths, manifest: dict[str, Any]) -> None:
    _write_json(job_paths.base / "manifest.json", manifest)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
