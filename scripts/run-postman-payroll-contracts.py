#!/usr/bin/env python3
"""Run the synthetic PDF and spreadsheet validation requests through Newman."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

REQUEST_NAMES = (
    "Preview a PDF payslip",
    "Import JSON (from last Preview)",
    "Import Spreadsheet (mode=validate)",
)


def parse_args() -> argparse.Namespace:
    """Parse runner arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--newman", default="newman")
    return parser.parse_args()


def find_requests(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Find the required requests while preserving their collection definitions."""
    found: dict[str, dict[str, Any]] = {}
    for item in items:
        if item.get("name") in REQUEST_NAMES and "request" in item:
            found[item["name"]] = item
        found.update(find_requests(item.get("item", [])))
    return found


def set_file_source(request: dict[str, Any], path: Path) -> None:
    """Set the sole file form-data source on a copied request."""
    formdata = request["request"]["body"]["formdata"]
    file_parts = [part for part in formdata if part.get("type") == "file"]
    if len(file_parts) != 1:
        raise ValueError(f"Expected one file part in {request['name']}")
    file_parts[0]["src"] = str(path)


def build_contract_collection(source: dict[str, Any], pdf: Path, xlsx: Path) -> dict[str, Any]:
    """Build a temporary collection containing only safe validation requests."""
    requests = find_requests(source.get("item", []))
    missing = [name for name in REQUEST_NAMES if name not in requests]
    if missing:
        raise ValueError(f"Collection is missing requests: {', '.join(missing)}")
    selected = [json.loads(json.dumps(requests[name])) for name in REQUEST_NAMES]
    set_file_source(selected[0], pdf)
    set_file_source(selected[2], xlsx)
    return {
        "info": {
            "name": "PF synthetic payroll contracts",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": source.get("variable", []),
        "item": selected,
    }


def main() -> int:
    """Materialize a disposable collection and execute Newman."""
    arguments = parse_args()
    source = json.loads(arguments.collection.read_text())
    collection = build_contract_collection(source, arguments.pdf, arguments.xlsx)
    with tempfile.TemporaryDirectory(prefix="pf-postman-contracts-") as directory:
        temporary_collection = Path(directory) / "collection.json"
        temporary_collection.write_text(json.dumps(collection))
        command = [
            arguments.newman,
            "run",
            str(temporary_collection),
            "--environment",
            str(arguments.environment),
            "--reporters",
            "cli,junit",
            "--reporter-junit-export",
            str(arguments.report),
            "--bail",
        ]
        completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
