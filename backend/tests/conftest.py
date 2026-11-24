from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app

MANAGER_HEADERS = {
    "X-Actor-Email": "manager@test.local",
    "X-Actor-Role": "claims_manager",
}
UNDERWRITER_HEADERS = {
    "X-Actor-Email": "uw@test.local",
    "X-Actor-Role": "underwriter",
}
ADJUSTER_HEADERS = {
    "X-Actor-Email": "adjuster@test.local",
    "X-Actor-Role": "adjuster",
}
VIEWER_HEADERS = {
    "X-Actor-Email": "viewer@test.local",
    "X-Actor-Role": "viewer",
}


def make_test_app(tmp_path: Path, **overrides: Any) -> FastAPI:
    """Create an isolated FastAPI app backed by a per-test SQLite file."""
    db_file = tmp_path / "test_insops.db"
    cfg = Settings(
        database_url=f"sqlite+aiosqlite:///{db_file.as_posix()}",
        llm_default_provider="mock",
        auto_create_tables=True,
        seed_demo_data=False,
        **overrides,
    )
    return create_app(cfg)


def build_minimal_pdf(pages_lines: list[list[str]]) -> bytes:
    """Build a valid single- or multi-page PDF containing extractable text lines."""
    num_pages = len(pages_lines)
    # Object layout:
    # 1: Catalog, 2: Pages, 3: Font
    # For each page i (0..N-1): page_obj = 4 + 2*i, content_obj = 5 + 2*i
    font_obj_num = 3
    page_obj_nums = [4 + 2 * i for i in range(num_pages)]

    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        (
            f"2 0 obj\n<< /Type /Pages /Kids [{' '.join(f'{n} 0 R' for n in page_obj_nums)}] "
            f"/Count {num_pages} >>\nendobj\n"
        ).encode("latin-1"),
        (
            f"{font_obj_num} 0 obj\n<< /Type /Font /Subtype /Type1 "
            "/BaseFont /Helvetica >>\nendobj\n"
        ).encode("latin-1"),
    ]

    for idx, lines in enumerate(pages_lines):
        page_num = 4 + 2 * idx
        content_num = 5 + 2 * idx
        escaped_ops: list[str] = []
        for line_idx, line in enumerate(lines):
            normalized = line.replace("—", "-").replace("–", "-")
            safe = normalized.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if line_idx == 0:
                escaped_ops.append(f"({safe}) Tj")
            else:
                escaped_ops.append(f"0 -16 Td ({safe}) Tj")
        stream_text = "BT /F1 11 Tf 50 740 Td " + " ".join(escaped_ops) + " ET"
        stream_bytes = stream_text.encode("latin-1")

        objects.append(
            (
                f"{page_num} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
                f"/Contents {content_num} 0 R >>\nendobj\n"
            ).encode("latin-1")
        )
        objects.append(
            (
                f"{content_num} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n"
            ).encode("latin-1")
            + stream_bytes
            + b"\nendstream\nendobj\n"
        )

    buf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(buf))
        buf.extend(obj)

    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    buf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    buf.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(buf)
