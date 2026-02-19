from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid


@dataclass(frozen=True)
class JobPaths:
    job_id: str
    base: Path
    audio: Path
    video: Path
    infographic: Path
    debug: Path


def generate_job_id() -> str:
    return uuid.uuid4().hex[:12]


def create_output_tree(out_dir: Path, job_id: str) -> JobPaths:
    base = out_dir / job_id
    paths = JobPaths(
        job_id=job_id,
        base=base,
        audio=base / "audio",
        video=base / "video",
        infographic=base / "infographic",
        debug=base / "debug",
    )

    for path in (paths.base, paths.audio, paths.video, paths.infographic, paths.debug):
        path.mkdir(parents=True, exist_ok=True)

    return paths
