#!/usr/bin/env python3
"""Run a synthetic pf-svc-income integration workflow against LOCAL only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SUCCESS_CODES = range(200, 300)


def parse_args() -> argparse.Namespace:
    """Parse local integration runner arguments."""
    parser = argparse.ArgumentParser(
        description="Run synthetic employer, contract, and template integration checks."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Local pf-svc-income base URL; non-local hosts are rejected.",
    )
    parser.add_argument(
        "--api-key-env",
        default="PF_INCOME_API_KEY",
        help="Environment variable containing the local API key.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the workflow boundary without creating data.",
    )
    parser.add_argument(
        "--defer-cleanup",
        action="store_true",
        help="Defer cleanup to the disposable local database wrapper.",
    )
    return parser.parse_args()


def ensure_local_url(base_url: str) -> str:
    """Reject non-local targets before any request can be sent."""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("Integration runner accepts localhost or loopback URLs only")
    return base_url.rstrip("/")


def response_body(response: bytes) -> object:
    """Decode a JSON response or return its text for diagnostics."""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return response.decode(errors="replace")


def matching_id(body: object, key: str, field: str, expected: object) -> int:
    """Extract the ID matching a fixture field from a batch response."""
    values = body if isinstance(body, list) else body.get(key) if isinstance(body, dict) else None
    if not isinstance(values, list):
        raise ValueError(f"Response did not contain a {key} list")
    for value in values:
        if isinstance(value, dict) and value.get(field) == expected:
            identifier = value.get("id")
            if isinstance(identifier, int):
                return identifier
    raise ValueError(f"Response did not contain a {key} item matching {field}={expected!r}")


def require_object_fields(body: object, fields: tuple[str, ...], context: str) -> dict[str, object]:
    """Assert a JSON object contains the domain fields required by a workflow."""
    if not isinstance(body, dict):
        raise ValueError(f"{context} response was not an object")
    missing = [field for field in fields if field not in body]
    if missing:
        raise ValueError(f"{context} response is missing fields: {', '.join(missing)}")
    return body


class LocalApi:
    """Minimal JSON client for the local income service."""

    def __init__(self, base_url: str, api_key: str) -> None:
        """Initialize the client."""
        self.base_url = base_url
        self.headers = {"Content-Type": "application/json", "X-API-Key": api_key}

    def request(self, method: str, path: str, body: object | None = None) -> object:
        """Send one request and fail with a sanitized status/path diagnostic."""
        request = Request(f"{self.base_url}{path}", method=method, headers=self.headers)
        if body is not None:
            request.data = json.dumps(body).encode()
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read()
                if response.status not in SUCCESS_CODES:
                    raise RuntimeError(f"Unexpected HTTP {response.status}: {method} {path}")
                return response_body(raw)
        except HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            raise RuntimeError(f"HTTP {error.code}: {method} {path}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Transport failure: {method} {path}: {error.reason}") from error


def run_workflow(client: LocalApi, *, defer_cleanup: bool = False) -> None:
    """Create, update, verify, and clean up synthetic integration data."""
    token = uuid.uuid4().hex[:10]
    employer_id: int | None = None
    contract_id: int | None = None
    template_id = f"imp-011-{token}"
    template_created = False
    primary_error: Exception | None = None
    try:
        employers = client.request(
            "POST",
            "/payroll/employers",
            {"employers": [{"name": f"IMP-011 Synthetic {token}", "tax_id": f"IMP011-{token}", "country_code": "CL"}]},
        )
        employer_id = matching_id(employers, "employers", "tax_id", f"IMP011-{token}")
        print(f"Synthetic employer created: {employer_id}")
        contracts = client.request(
            "POST",
            "/payroll/contracts",
            {"contracts": [{"employer_id": employer_id, "started_at": "2026-01-01", "ended_at": None, "is_indefinite": True, "position": "Synthetic integration position"}]},
        )
        contract_id = matching_id(contracts, "contracts", "employer_id", employer_id)
        created_template = require_object_fields(
            client.request(
                "POST",
                "/payroll/templates",
                {"template_id": template_id, "employer_id": employer_id, "employer_match_pattern": f"(?i){token}", "version": 1, "fields": [{"pdf_label_pattern": "(?i)^SUELDO$", "concept_code": "SALARY_BASE", "confidence": 0.9}]},
            ),
            ("template_id", "version", "fields", "is_active"),
            "Create template",
        )
        if created_template["template_id"] != template_id or created_template["version"] != 1:
            raise ValueError("Create template response did not echo the fixture identity/version")
        template_created = True
        updated_template = require_object_fields(
            client.request(
                "PUT",
                f"/payroll/templates/{template_id}",
                {"employer_id": employer_id, "employer_match_pattern": f"(?i){token}", "version": 2, "fields": [{"pdf_label_pattern": "(?i)^SUELDO\\s*BASE$", "concept_code": "SALARY_BASE", "confidence": 0.95}]},
            ),
            ("template_id", "version", "fields", "is_active"),
            "Update template",
        )
        if updated_template["template_id"] != template_id or updated_template["version"] != 2:
            raise ValueError("Update template response did not echo the fixture identity/version")
        reread_template = require_object_fields(
            client.request("GET", f"/payroll/templates/{template_id}"),
            ("template_id", "version", "fields", "is_active"),
            "Get updated template",
        )
        if reread_template["version"] != 2:
            raise ValueError("Updated template could not be read back with version 2")
        print("Integration workflow passed: employer, contract, template create/update/read")
    except Exception as error:  # noqa: BLE001 - cleanup must preserve the primary error
        primary_error = error
    finally:
        cleanup_errors: list[str] = []
        if template_created:
            try:
                client.request("DELETE", f"/payroll/templates/{template_id}")
            except Exception as error:  # noqa: BLE001 - cleanup must continue
                cleanup_errors.append(f"template: {error}")
        if contract_id is not None:
            try:
                client.request("DELETE", "/payroll/contracts", {"ids": [contract_id]})
            except Exception as error:  # noqa: BLE001 - cleanup must continue
                cleanup_errors.append(f"contract: {error}")
        if employer_id is not None:
            try:
                client.request("DELETE", "/payroll/employers", {"ids": [employer_id]})
            except Exception as error:  # noqa: BLE001 - cleanup must continue
                cleanup_errors.append(f"employer: {error}")
        if cleanup_errors and not defer_cleanup:
            cleanup_error = RuntimeError("Cleanup failed: " + "; ".join(cleanup_errors))
            if primary_error is not None:
                raise RuntimeError(f"Setup failed: {primary_error}; {cleanup_error}") from primary_error
            raise cleanup_error
        if cleanup_errors and defer_cleanup:
            print("Cleanup deferred to disposable local database reset: " + "; ".join(cleanup_errors))
        if primary_error is not None:
            raise primary_error
        print("Cleanup passed: template, contract, employer")


def main() -> int:
    """Run the guarded local integration workflow."""
    arguments = parse_args()
    try:
        base_url = ensure_local_url(arguments.base_url)
        if arguments.dry_run:
            print("Dry run only: LOCAL employer → contract → template create/update → cleanup")
            return 0
        api_key = os.environ.get(arguments.api_key_env, "")
        if not api_key:
            raise ValueError(f"Missing API key environment variable: {arguments.api_key_env}")
        run_workflow(
            LocalApi(base_url, api_key),
            defer_cleanup=arguments.defer_cleanup,
        )
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
