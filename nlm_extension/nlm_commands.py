from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence


class NlmErrorKind(str, Enum):
    COMMAND_FAILURE = "command_failure"
    PARSE_FAILURE = "parse_failure"
    TIMEOUT = "timeout"
    AUTH_SESSION = "auth_session"


@dataclass(frozen=True)
class CommandResult:
    args: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    attempts: int


class NlmCommandError(RuntimeError):
    def __init__(
        self,
        kind: NlmErrorKind,
        message: str,
        *,
        command: Sequence[str] | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.command = list(command) if command else None
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class NotebookSummary:
    notebook_id: str
    title: str


@dataclass(frozen=True)
class OverviewJob:
    notebook_id: str
    status: str
    audio_id: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class AudioAsset:
    notebook_id: str
    file_name: str
    format: str
    path: str
    size_mb: float | None = None


class NlmClient:
    def __init__(
        self,
        executable: str = "nlm",
        *,
        timeout_s: float = 30.0,
        retries: int = 1,
        retry_delay_s: float = 0.5,
    ) -> None:
        self.executable = executable
        self.timeout_s = timeout_s
        self.retries = retries
        self.retry_delay_s = retry_delay_s

    def run_command(
        self,
        args: Iterable[str],
        *,
        timeout_s: float | None = None,
        retries: int | None = None,
    ) -> CommandResult:
        argv = [self.executable, *list(args)]
        max_attempts = (retries if retries is not None else self.retries) + 1
        timeout = timeout_s if timeout_s is not None else self.timeout_s

        last_error: NlmCommandError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                completed = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                last_error = NlmCommandError(
                    NlmErrorKind.TIMEOUT,
                    f"Command timed out after {timeout}s",
                    command=argv,
                    stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                    stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                )
            else:
                if completed.returncode == 0:
                    return CommandResult(
                        args=argv,
                        returncode=completed.returncode,
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                        attempts=attempt,
                    )

                kind = self._classify_error(completed.stdout, completed.stderr)
                last_error = NlmCommandError(
                    kind,
                    f"Command failed with exit code {completed.returncode}",
                    command=argv,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )

            if attempt < max_attempts:
                time.sleep(self.retry_delay_s)

        assert last_error is not None
        raise last_error

    def create_notebook(self, title: str) -> str:
        # tmc/nlm: `nlm create <title>` prints notebook ID on success.
        result = self.run_command(["create", title])
        return self._extract_last_identifier(
            result,
            error_message="Notebook creation output missing notebook id",
        )

    def select_notebook(self, identifier: str) -> str:
        # tmc/nlm has no direct `select`; we resolve from `nlm ls` by id or title.
        notebooks = self.list_notebooks()
        for notebook in notebooks:
            normalized_title = notebook.title.lstrip("📙").strip()
            if identifier in {notebook.notebook_id, notebook.title, normalized_title}:
                return notebook.notebook_id
        raise NlmCommandError(
            NlmErrorKind.PARSE_FAILURE,
            f"Notebook '{identifier}' not found in nlm ls output",
        )

    def upload_pdf_source(self, notebook_id: str, pdf_path: str | Path) -> str:
        # tmc/nlm: `nlm add <id> <input>` logs progress + prints source id on last line.
        result = self.run_command(["add", notebook_id, str(pdf_path)])
        return self._extract_last_identifier(
            result,
            error_message="Source upload output missing source id",
        )

    def trigger_audio_overview(self, notebook_id: str, instructions: str) -> OverviewJob:
        # tmc/nlm: `nlm audio-create <id> <instructions>` emits text status.
        result = self.run_command(["audio-create", notebook_id, instructions])
        output = self._combined_output(result)
        if "creation started" in output.lower():
            return OverviewJob(notebook_id=notebook_id, status="queued")
        if "audio overview created" in output.lower():
            audio_id = self._extract_field(output, "ID")
            title = self._extract_field(output, "Title")
            return OverviewJob(notebook_id=notebook_id, status="completed", audio_id=audio_id, title=title)
        raise NlmCommandError(
            NlmErrorKind.PARSE_FAILURE,
            "Unable to parse audio-create output",
            command=result.args,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def poll_overview_completion(
        self,
        notebook_id: str,
        *,
        interval_s: float = 2.0,
        timeout_s: float = 600.0,
    ) -> OverviewJob:
        start = time.monotonic()
        while True:
            if time.monotonic() - start > timeout_s:
                raise NlmCommandError(
                    NlmErrorKind.TIMEOUT,
                    f"Timed out waiting for audio overview for notebook {notebook_id}",
                )

            result = self.run_command(["audio-get", notebook_id])
            output = self._combined_output(result)
            lowered = output.lower()
            if "not ready yet" in lowered:
                time.sleep(interval_s)
                continue
            if "audio overview:" in lowered:
                return OverviewJob(
                    notebook_id=notebook_id,
                    status="completed",
                    audio_id=self._extract_field(output, "ID"),
                    title=self._extract_field(output, "Title"),
                )
            raise NlmCommandError(
                NlmErrorKind.PARSE_FAILURE,
                "Unable to parse audio-get output while polling",
                command=result.args,
                stdout=result.stdout,
                stderr=result.stderr,
            )

    def download_audio_assets(self, notebook_id: str, output_path: str | Path | None = None) -> list[AudioAsset]:
        args = ["audio-download", notebook_id]
        if output_path is not None:
            args.append(str(output_path))
        result = self.run_command(args)
        output = self._combined_output(result)
        file_name = self._extract_saved_file(output)
        if not file_name:
            raise NlmCommandError(
                NlmErrorKind.PARSE_FAILURE,
                "Audio download output missing saved file path",
                command=result.args,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        ext = Path(file_name).suffix.lstrip(".") or "unknown"
        size_mb = self._extract_size_mb(output)
        return [
            AudioAsset(
                notebook_id=notebook_id,
                file_name=Path(file_name).name,
                format=ext,
                path=file_name,
                size_mb=size_mb,
            )
        ]

    def list_notebooks(self) -> list[NotebookSummary]:
        result = self.run_command(["ls"])
        rows = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("Total notebooks") or line.startswith("ID"):
                continue
            m = re.match(r"^(?P<id>[a-f0-9-]{16,})\s+(?P<title>.+?)\s+\d+\s+\d{4}-\d{2}-\d{2}T", line, re.IGNORECASE)
            if m:
                rows.append(NotebookSummary(notebook_id=m.group("id"), title=m.group("title").strip()))
        if not rows:
            raise NlmCommandError(
                NlmErrorKind.PARSE_FAILURE,
                "Unable to parse nlm ls output",
                command=result.args,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return rows

    def manifest_entry(
        self,
        *,
        notebook_id: str,
        source_id: str,
        job: OverviewJob,
        assets: Sequence[AudioAsset],
    ) -> dict[str, Any]:
        return {
            "notebook_id": notebook_id,
            "source_id": source_id,
            "audio_overview": {
                "status": job.status,
                "audio_id": job.audio_id,
                "title": job.title,
            },
            "assets": [
                {
                    "notebook_id": asset.notebook_id,
                    "file_name": asset.file_name,
                    "format": asset.format,
                    "path": asset.path,
                    "size_mb": asset.size_mb,
                }
                for asset in assets
            ],
        }

    def _extract_last_identifier(self, result: CommandResult, *, error_message: str) -> str:
        for line in reversed(result.stdout.splitlines()):
            value = line.strip()
            if value and re.fullmatch(r"[a-zA-Z0-9_-]{6,}", value):
                return value
        raise NlmCommandError(
            NlmErrorKind.PARSE_FAILURE,
            error_message,
            command=result.args,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _extract_field(self, output: str, field_name: str) -> str | None:
        pattern = rf"^\s*{re.escape(field_name)}:\s*(.+)$"
        for line in output.splitlines():
            m = re.match(pattern, line)
            if m:
                value = m.group(1).strip()
                return value if value else None
        return None

    def _extract_saved_file(self, output: str) -> str | None:
        for line in output.splitlines():
            m = re.match(r"^\s*✅\s+Audio saved to:\s*(.+)$", line)
            if m:
                return m.group(1).strip()
        return None

    def _extract_size_mb(self, output: str) -> float | None:
        for line in output.splitlines():
            m = re.match(r"^\s*File size:\s*([0-9]+(?:\.[0-9]+)?)\s*MB\s*$", line)
            if m:
                return float(m.group(1))
        return None

    def _combined_output(self, result: CommandResult) -> str:
        return f"{result.stdout}\n{result.stderr}".strip()

    def _classify_error(self, stdout: str, stderr: str) -> NlmErrorKind:
        haystack = f"{stdout}\n{stderr}".lower()
        auth_markers = (
            "authentication required",
            "not authenticated",
            "unauthorized",
            "forbidden",
            "invalid token",
            "session expired",
            "login required",
            "cookie invalid",
        )
        if any(marker in haystack for marker in auth_markers):
            return NlmErrorKind.AUTH_SESSION
        return NlmErrorKind.COMMAND_FAILURE
