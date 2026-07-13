"""Offline data ingestion CLI."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.settings import load_settings
from ingestion import IngestionPipeline, IngestionPipelineError, IngestionResult


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}


def main(
    argv: Sequence[str] | None = None,
    pipeline_factory: Callable[[Any], IngestionPipeline] | None = None,
) -> int:
    """Parse CLI arguments, run ingestion, and return a process exit code."""
    args = _parse_args(argv)
    try:
        paths = _resolve_paths(args.path)
        settings = load_settings(args.settings)
        pipeline = (
            pipeline_factory(settings)
            if pipeline_factory is not None
            else IngestionPipeline(settings=settings)
        )
        results = [
            pipeline.run(path, collection=args.collection, force=args.force)
            for path in paths
        ]
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1

    _print_summary(results)
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline document ingestion.")
    parser.add_argument(
        "--path",
        required=True,
        help="File or directory to ingest. Directories are searched recursively.",
    )
    parser.add_argument(
        "--collection",
        default="default",
        help="Target collection name. Defaults to 'default'.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even when integrity history says the file is unchanged.",
    )
    parser.add_argument(
        "--settings",
        default=str(PROJECT_ROOT / "config" / "settings.yaml"),
        help="Path to settings.yaml.",
    )
    return parser.parse_args(argv)


def _resolve_paths(path: str | Path) -> list[Path]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"ingestion path does not exist: {source}")
    if source.is_file():
        if source.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported file type: {source.suffix or '<none>'}")
        return [source]

    paths = sorted(
        item
        for item in source.rglob("*")
        if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not paths:
        raise ValueError(f"no supported documents found under: {source}")
    return paths


def _print_summary(results: list[IngestionResult]) -> None:
    for result in results:
        status = "SKIPPED" if result.skipped else "INGESTED"
        document_id = result.document_id or "-"
        print(
            f"{status} document={document_id} chunks={result.chunk_count} "
            f"records={result.record_count} images={result.image_count}"
        )
    ingested = sum(1 for result in results if not result.skipped)
    skipped = sum(1 for result in results if result.skipped)
    print(f"Summary: ingested={ingested} skipped={skipped} total={len(results)}")


if __name__ == "__main__":
    raise SystemExit(main())
