#!/usr/bin/env python3
"""Compare service OpenAPI operations with requests in the Postman collection."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


SERVICE_FOLDER_NAMES = {"pf-rates", "pf-svc-income"}
INTENTIONAL_DUPLICATES = {
    ("pf-rates", "POST", "/economic-indices/refresh"),
    ("pf-rates", "POST", "/exchange-rates/refresh"),
    ("pf-rates", "POST", "/exports/financial-data"),
    ("pf-svc-income", "POST", "/payroll/import/json"),
}
PATH_PARAMETER_PATTERN = re.compile(r":([A-Za-z0-9_]+)")


def parse_args() -> argparse.Namespace:
    """Parse coverage checker arguments."""
    parser = argparse.ArgumentParser(
        description="Check OpenAPI operations represented in a Postman collection."
    )
    parser.add_argument(
        "--collection",
        type=Path,
        default=Path("pf-ecosystem.postman_collection.json"),
        help="Postman collection JSON file.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--openapi",
        action="append",
        metavar="SERVICE=FILE",
        help="OpenAPI JSON file, repeated once per service.",
    )
    source_group.add_argument(
        "--openapi-url",
        action="append",
        metavar="SERVICE=URL",
        help="OpenAPI URL, repeated once per service; fetched with GET.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds for --openapi-url (default: 15).",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from ``path``."""
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def normalize_path(path: str) -> str:
    """Normalize OpenAPI and Postman path parameter notation."""
    parsed = urlsplit(path)
    normalized = parsed.path or "/"
    normalized = re.sub(r"^/?\{\{[^{}]+\}\}", "", normalized)
    normalized = re.sub(r"\{\{([^{}]+)\}\}", r"{\1}", normalized)
    normalized = PATH_PARAMETER_PATTERN.sub(r"{\1}", normalized)
    normalized = re.sub(r"/{2,}", "/", normalized)
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized


def operation_key(method: str, path: str) -> tuple[str, str]:
    """Return a comparable method/path key."""
    return method.upper(), normalize_path(path)


def openapi_operations(document: dict[str, Any]) -> set[tuple[str, str]]:
    """Extract HTTP operations from an OpenAPI document."""
    paths = document.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI document has no object-valued 'paths' field")
    operations: set[tuple[str, str]] = set()
    for path, definition in paths.items():
        if not isinstance(definition, dict):
            continue
        for method in definition:
            if method.lower() in {"summary", "description", "parameters", "servers"}:
                continue
            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                operations.add(operation_key(method, path))
    return operations


def request_path(request: dict[str, Any]) -> str | None:
    """Extract a comparable path from a Postman request object."""
    url = request.get("url")
    if isinstance(url, str):
        return normalize_path(url)
    if not isinstance(url, dict):
        return None
    raw = url.get("raw")
    if isinstance(raw, str):
        return normalize_path(raw)
    path = url.get("path")
    if isinstance(path, list):
        return normalize_path("/" + "/".join(str(segment) for segment in path))
    return None


def postman_operations(collection: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Extract method/path operations grouped by top-level service folder."""
    services: dict[str, list[tuple[str, str]]] = {}
    for service in collection.get("item", []):
        if not isinstance(service, dict) or service.get("name") not in SERVICE_FOLDER_NAMES:
            continue
        found: list[tuple[str, str]] = []

        def visit(items: list[Any]) -> None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                request = item.get("request")
                if isinstance(request, dict):
                    method = request.get("method")
                    path = request_path(request)
                    if isinstance(method, str) and path is not None:
                        found.append(operation_key(method, path))
                children = item.get("item")
                if isinstance(children, list):
                    visit(children)

        children = service.get("item", [])
        if isinstance(children, list):
            visit(children)
        services[service["name"]] = found
    return services


def parse_service_arguments(values: list[str]) -> dict[str, str]:
    """Parse repeated ``SERVICE=VALUE`` arguments."""
    result: dict[str, str] = {}
    for value in values:
        service, separator, filename = value.partition("=")
        if not separator or not service or not filename:
            raise ValueError(f"Invalid --openapi value {value!r}; expected SERVICE=FILE")
        if service in result:
            raise ValueError(f"Duplicate OpenAPI service: {service}")
        result[service] = filename
    return result


def fetch_openapi(url: str, timeout: float) -> dict[str, Any]:
    """Fetch one OpenAPI document without sending credentials."""
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "pf-postman-coverage"})
    with urlopen(request, timeout=timeout) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"OpenAPI URL returned a non-object document: {url}")
    return value


def format_operation(operation: tuple[str, str]) -> str:
    """Format an operation for human-readable output."""
    method, path = operation
    return f"{method} {path}"


def check(
    collection_path: Path,
    openapi_paths: dict[str, str],
    source_type: str,
    timeout: float,
) -> int:
    """Print coverage differences and return a process exit code."""
    collection = load_json(collection_path)
    postman = postman_operations(collection)
    expected_services = set(openapi_paths)
    missing_services = expected_services - set(postman)
    if missing_services:
        for service in sorted(missing_services):
            print(f"MISSING SERVICE FOLDER: {service}")

    failed = bool(missing_services)
    for service in sorted(expected_services & set(postman)):
        document = (
            load_json(Path(openapi_paths[service]))
            if source_type == "file"
            else fetch_openapi(openapi_paths[service], timeout)
        )
        expected = openapi_operations(document)
        actual_items = postman[service]
        actual = set(actual_items)
        duplicates = sorted(
            operation
            for operation, count in Counter(actual_items).items()
            if count > 1
            and (service, operation[0], operation[1]) not in INTENTIONAL_DUPLICATES
        )
        missing = sorted(expected - actual)
        stale = sorted(actual - expected)
        print(f"{service}: expected={len(expected)} postman={len(actual_items)}")
        for operation in missing:
            print(f"  MISSING {format_operation(operation)}")
        for operation in stale:
            print(f"  STALE   {format_operation(operation)}")
        for operation in duplicates:
            print(f"  DUPLICATE {format_operation(operation)}")
        failed = failed or bool(missing or stale or duplicates)
    return int(failed)


def main() -> int:
    """Run the coverage check and convert input errors into a clear failure."""
    arguments = parse_args()
    try:
        source_type = "file" if arguments.openapi is not None else "url"
        values = arguments.openapi if arguments.openapi is not None else arguments.openapi_url
        openapi_paths = parse_service_arguments(values or [])
        return check(arguments.collection, openapi_paths, source_type, arguments.timeout)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
