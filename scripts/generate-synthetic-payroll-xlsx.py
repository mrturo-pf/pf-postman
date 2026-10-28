#!/usr/bin/env python3
"""Generate a minimal synthetic spreadsheet accepted by payroll validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from openpyxl import Workbook


def main() -> int:
    """Write a deterministic spreadsheet fixture."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["period_month", "period_year", "employer", "payment_date", "salary_base"])
    sheet.append([10, 2026, "WALMART-CHILE", "2026-10-31", 1_000_000])
    workbook.save(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
