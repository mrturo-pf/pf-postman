#!/usr/bin/env python3
"""Run the read-only Postman smoke subset with Newman."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}


def parse_args() -> argparse.Namespace:
    """Parse smoke-runner arguments."""
    parser = argparse.ArgumentParser(description="Run read-only Postman requests with Newman.")
    parser.add_argument(
        "--collection",
        type=Path,
        default=Path("pf-ecosystem.postman_collection.json"),
        help="Postman collection JSON file.",
    )
    parser.add_argument(
        "--environment",
        type=Path,
        required=True,
        help="Postman environment JSON file.",
    )
    parser.add_argument(
        "--newman",
        default="newman",
        help="Newman executable (default: newman; use npx newman through a shell if needed).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("test-results/postman-smoke.xml"),
        help="JUnit report destination.",
    )
    parser.add_argument(
        "--include-sheets",
        action="store_true",
        help="Include pf-sheets requests; disabled by default because its URL is external.",
    )
    parser.add_argument(
        "--include-job-status",
        action="store_true",
        help="Include status for a specific export job ID; disabled by default because IDs are not stable fixtures.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the filtered collection and print its request count without running Newman.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def filter_items(items: list[Any], include_job_status: bool = False) -> tuple[list[Any], int]:
    """Keep only read-only requests while preserving folder structure."""
    filtered: list[Any] = []
    request_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("name") == "Get export job status" and not include_job_status:
            continue
        request = item.get("request")
        if isinstance(request, dict):
            if str(request.get("method", "")).upper() in READ_ONLY_METHODS:
                filtered.append(item)
                request_count += 1
            continue
        children = item.get("item")
        if isinstance(children, list):
            child_items, child_count = filter_items(children, include_job_status)
            if child_items:
                folder = dict(item)
                folder["item"] = child_items
                filtered.append(folder)
                request_count += child_count
    return filtered, request_count


def build_smoke_collection(
    collection: dict[str, Any], include_sheets: bool = False, include_job_status: bool = False
) -> tuple[dict[str, Any], int]:
    """Return a collection containing only read-only requests."""
    smoke = dict(collection)
    source_items = [
        item
        for item in collection.get("item", [])
        if include_sheets or not isinstance(item, dict) or item.get("name") != "pf-sheets"
    ]
    items, request_count = filter_items(source_items)
    smoke["item"] = items
    return smoke, request_count


def main() -> int:
    """Build a temporary smoke collection and execute Newman."""
    arguments = parse_args()
    try:
        collection = read_json(arguments.collection)
        read_only_collection, request_count = build_smoke_collection(
            collection,
            include_sheets=arguments.include_sheets,
            include_job_status=arguments.include_job_status,
        )
        if request_count == 0:
            raise ValueError("No read-only requests found in the collection")
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pf-postman-smoke-") as directory:
            temporary_collection = Path(directory) / "smoke-collection.json"
            temporary_collection.write_text(
                json.dumps(read_only_collection, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"Read-only requests selected: {request_count}")
            if arguments.dry_run:
                print(f"Filtered collection: {temporary_collection}")
                return 0
            if shutil.which(arguments.newman) is None:
                raise FileNotFoundError(
                    f"Newman executable not found: {arguments.newman}. Install Newman before running smoke tests."
                )
            command = [
                arguments.newman,
                "run",
                str(temporary_collection),
                "--environment",
                str(arguments.environment.resolve()),
                "--bail",
                "--reporters",
                "cli,junit",
                "--reporter-junit-export",
                str(arguments.report.resolve()),
            ]
            return subprocess.run(command, check=False).returncode
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
