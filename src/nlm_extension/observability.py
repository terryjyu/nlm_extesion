from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping


MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "input",
        "notebook",
        "audio_assets",
        "video",
        "infographic_assets",
        "timing",
        "diagnostics",
    ],
    "properties": {
        "input": {
            "type": "object",
            "required": ["path", "hash"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "hash": {"type": "string", "minLength": 1},
            },
        },
        "notebook": {
            "type": "object",
            "required": ["id", "url"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "url": {"type": "string", "minLength": 1},
            },
        },
        "audio_assets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "path", "duration_seconds"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "duration_seconds": {"type": "number", "minimum": 0},
                },
            },
        },
        "video": {
            "type": "object",
            "required": ["duration_seconds"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "share_link": {"type": "string", "minLength": 1},
                "duration_seconds": {"type": "number", "minimum": 0},
            },
            "oneOf": [
                {"required": ["path"]},
                {"required": ["share_link"]},
            ],
        },
        "infographic_assets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "path"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                },
            },
        },
        "timing": {
            "type": "object",
            "required": ["started_at", "ended_at", "total_duration_seconds"],
            "properties": {
                "started_at": {"type": "string", "minLength": 1},
                "ended_at": {"type": "string", "minLength": 1},
                "total_duration_seconds": {"type": "number", "minimum": 0},
            },
        },
        "diagnostics": {
            "type": "object",
            "required": ["log_path", "failure_png_path", "failure_html_path"],
            "properties": {
                "log_path": {"type": "string", "minLength": 1},
                "failure_png_path": {"type": "string", "minLength": 1},
                "failure_html_path": {"type": "string", "minLength": 1},
            },
        },
    },
}


def _require_keys(payload: Mapping[str, Any], required: list[str], section: str) -> None:
    for key in required:
        if key not in payload:
            raise ValueError(f"Missing required field '{section}.{key}'")


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    _require_keys(manifest, MANIFEST_SCHEMA["required"], "manifest")

    input_block = manifest["input"]
    _require_keys(input_block, ["path", "hash"], "input")

    notebook_block = manifest["notebook"]
    _require_keys(notebook_block, ["id", "url"], "notebook")

    video_block = manifest["video"]
    _require_keys(video_block, ["duration_seconds"], "video")
    if "path" not in video_block and "share_link" not in video_block:
        raise ValueError("Video must include either 'path' or 'share_link'.")

    timing_block = manifest["timing"]
    _require_keys(timing_block, ["started_at", "ended_at", "total_duration_seconds"], "timing")

    diagnostics_block = manifest["diagnostics"]
    _require_keys(
        diagnostics_block,
        ["log_path", "failure_png_path", "failure_html_path"],
        "diagnostics",
    )


def write_manifest(manifest: Mapping[str, Any], destination: str | Path) -> Path:
    validate_manifest(manifest)
    output_path = Path(destination)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: MutableMapping[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def create_run_logger(job_id: str, out_root: str | Path = "out") -> tuple[logging.Logger, Path]:
    log_dir = Path(out_root) / job_id / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "run.log"

    logger_name = f"nlm_extension.run.{job_id}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)

    return logger, log_path


FALLBACK_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01"
    b"\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def capture_failure_artifacts(job_id: str, out_root: str | Path = "out", page: Any | None = None) -> dict[str, Path]:
    debug_dir = Path(out_root) / job_id / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    png_path = debug_dir / "failure.png"
    html_path = debug_dir / "page.html"

    png_bytes = None
    html_text = None

    if page is not None:
        screenshot = getattr(page, "screenshot", None)
        if callable(screenshot):
            try:
                png_bytes = screenshot()
            except Exception:
                png_bytes = None

        content = getattr(page, "content", None)
        if callable(content):
            try:
                html_text = content()
            except Exception:
                html_text = None

    png_path.write_bytes(png_bytes if png_bytes else FALLBACK_PNG_BYTES)
    html_path.write_text(html_text if html_text else "<html><body>failure capture unavailable</body></html>", encoding="utf-8")

    return {"failure_png_path": png_path, "failure_html_path": html_path}
