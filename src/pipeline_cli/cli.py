from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import ExitCode, PipelineError
from .job import create_output_tree, generate_job_id
from .orchestrator import RunConfig, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description="Pipeline command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the pipeline")
    run_parser.add_argument("--pdf", required=True, help="Path to input PDF")
    run_parser.add_argument("--out", default="out", help="Output root directory")
    run_parser.add_argument("--notebook-name", default="default-notebook", help="Notebook name")
    run_parser.add_argument("--headful", action="store_true", help="Run notebook ingest in headful mode")

    return parser


def parse_run_args(args: argparse.Namespace) -> tuple[RunConfig, Path]:
    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists() or not pdf_path.is_file():
        raise PipelineError(
            code=ExitCode.INPUT_NOT_FOUND,
            message="Input PDF does not exist",
            details={"pdf": str(pdf_path)},
        )
    if pdf_path.suffix.lower() != ".pdf":
        raise PipelineError(
            code=ExitCode.INVALID_ARGUMENT,
            message="Input file must be a .pdf",
            details={"pdf": str(pdf_path)},
        )

    out_dir = Path(args.out).expanduser().resolve()
    return (
        RunConfig(
            pdf=pdf_path,
            notebook_name=args.notebook_name,
            headful=args.headful,
        ),
        out_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)

        if args.command != "run":
            raise PipelineError(code=ExitCode.INVALID_ARGUMENT, message="Unknown command")

        config, out_dir = parse_run_args(args)
        job_id = generate_job_id()
        paths = create_output_tree(out_dir=out_dir, job_id=job_id)

        manifest = run_pipeline(config=config, job_paths=paths)
        print(json.dumps(manifest, indent=2))
        return int(ExitCode.SUCCESS)
    except PipelineError as err:
        print(json.dumps(err.to_payload()), file=sys.stderr)
        return int(err.code)
    except Exception as err:  # pragma: no cover
        payload = PipelineError(
            code=ExitCode.UNEXPECTED_ERROR,
            message="Unexpected error",
            details={"reason": str(err)},
        )
        print(json.dumps(payload.to_payload()), file=sys.stderr)
        return int(ExitCode.UNEXPECTED_ERROR)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
