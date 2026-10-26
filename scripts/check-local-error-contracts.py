#!/usr/bin/env python3
"""Validate expected HTTP error contracts against loopback PF services."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    """Parse local error-contract checker arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rates-url", default="http://localhost:8001")
    parser.add_argument("--income-url", default="http://localhost:8000")
    parser.add_argument("--rates-key-env", default="PF_RATES_API_KEY")
    parser.add_argument("--income-key-env", default="PF_INCOME_API_KEY")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow explicitly supplied non-loopback URLs; use only for the read-only GCP workflow.",
    )
    return parser.parse_args()


def target_url(value: str, allow_remote: bool) -> str:
    """Validate loopback targets, or explicitly approved HTTPS remote targets."""
    parsed = urlparse(value)
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return value.rstrip("/")
    if allow_remote and parsed.scheme == "https" and parsed.hostname:
        return value.rstrip("/")
    raise ValueError("Error-contract checker accepts loopback URLs, or explicit HTTPS remote mode")


def request_status(
    base_url: str, path: str, *, api_key: str, method: str = "GET", body: object | None = None
) -> int:
    """Return an HTTP status without printing response bodies."""
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    request = Request(f"{base_url}{path}", method=method, headers=headers)
    if body is not None:
        request.data = json.dumps(body).encode()
    try:
        with urlopen(request, timeout=15) as response:
            return response.status
    except HTTPError as error:
        return error.code


def check_case(name: str, actual: int, expected: set[int]) -> None:
    """Fail with a concise diagnostic when a status is outside its contract."""
    if actual not in expected:
        expected_text = ", ".join(str(status) for status in sorted(expected))
        raise RuntimeError(f"{name}: expected {expected_text}, received {actual}")
    print(f"PASS {name}: HTTP {actual}")


def main() -> int:
    """Run safe local error-contract cases."""
    arguments = parse_args()
    try:
        rates_url = target_url(arguments.rates_url, arguments.allow_remote)
        income_url = target_url(arguments.income_url, arguments.allow_remote)
        rates_key = os.environ.get(arguments.rates_key_env, "")
        income_key = os.environ.get(arguments.income_key_env, "")
        if not rates_key or not income_key:
            raise ValueError("Both local API key environment variables are required")

        check_case(
            "pf-rates invalid API key",
            request_status(rates_url, "/monetary-units", api_key="invalid-local-key"),
            {401, 403},
        )
        check_case(
            "pf-svc-income invalid API key",
            request_status(income_url, "/payroll/employers", api_key="invalid-local-key"),
            {401, 403},
        )
        check_case(
            "pf-svc-income missing payroll",
            request_status(income_url, "/payroll/999999999", api_key=income_key),
            {404},
        )
        check_case(
            "pf-svc-income missing template",
            request_status(income_url, "/payroll/templates/imp-011-missing", api_key=income_key),
            {404},
        )
        check_case(
            "pf-svc-income empty JSON import",
            request_status(
                income_url,
                "/payroll/import/json",
                api_key=income_key,
                method="POST",
                body={"mode": "validate", "periods": []},
            ),
            {400, 422},
        )
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
