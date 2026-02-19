"""Core helpers for NotebookLM pipeline automation."""

from .nlm_commands import (
    AudioAsset,
    CommandResult,
    NlmClient,
    NlmCommandError,
    NlmErrorKind,
    NotebookSummary,
    OverviewJob,
)
from .observability import (
    MANIFEST_SCHEMA,
    capture_failure_artifacts,
    create_run_logger,
    validate_manifest,
    write_manifest,
)

__all__ = [
    "AudioAsset",
    "CommandResult",
    "NlmClient",
    "NlmCommandError",
    "NlmErrorKind",
    "NotebookSummary",
    "OverviewJob",
    "MANIFEST_SCHEMA",
    "capture_failure_artifacts",
    "create_run_logger",
    "validate_manifest",
    "write_manifest",
]
