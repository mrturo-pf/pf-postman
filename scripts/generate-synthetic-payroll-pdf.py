#!/usr/bin/env python3
"""Generate a deterministic, text-layer PDF for local payroll preview tests."""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_LINES = (
    "WALMART-CHILE",
    "octubre 2026",
    "DIAS TRABAJADOS",
    "30",
    "DETALLE",
    "SUELDO 1.000.000",
    "IMPUESTO 50.000",
    "COT. SEG. CES. 10.000",
    "TOTALES",
    "LIQUIDO A PAGAR 940.000",
)


def parse_args() -> argparse.Namespace:
    """Parse PDF generator arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output PDF path; intended for a temporary local fixture.",
    )
    return parser.parse_args()


def pdf_bytes(lines: tuple[str, ...] = DEFAULT_LINES) -> bytes:
    """Build a minimal valid PDF with deterministic text content."""
    objects: list[tuple[int, str]] = [
        (1, "<< /Type /Catalog /Pages 2 0 R >>"),
        (2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        (
            3,
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        ),
        (4, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    text = "BT /F1 12 Tf 72 740 Td 16 TL " + " ".join(
        f"({line}) Tj T*" for line in lines
    ) + " ET"
    objects.append((5, f"<< /Length {len(text.encode())} >>\nstream\n{text}\nendstream"))

    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in objects:
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n{body}\nendobj\n".encode())

    cross_reference_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{cross_reference_offset}\n%%EOF\n".encode()
    )
    return bytes(document)


def main() -> int:
    """Write the deterministic synthetic PDF."""
    arguments = parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(pdf_bytes())
    print(f"Generated synthetic payroll PDF: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
