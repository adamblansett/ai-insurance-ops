import io
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pypdf import PdfReader

from app.db.base import parse_iso_date, quantize_money, utcnow
from app.intake.embeddings import extract_keywords


@dataclass
class ParsedClause:
    clause_type: str
    section_ref: str
    page_number: int
    title: str
    clause_text: str
    monetary_limit: Decimal | None
    deductible_override: Decimal | None
    keywords: list[str]


@dataclass
class ParsedPolicy:
    policy_number: str
    carrier_name: str
    named_insured: str
    insured_address: str
    line_of_business: str
    acord_form_type: str
    effective_date: date
    expiration_date: date
    status: str
    per_occurrence_limit: Decimal
    aggregate_limit: Decimal
    deductible: Decimal
    annual_premium: Decimal
    raw_text: str
    schedules: list[dict[str, Any]]
    clauses: list[ParsedClause]
    extraction_confidence: float


_PAGE_MARKER_RE = re.compile(r"(?im)^\s*(?:---\s*page\s+(\d+)\s*---|\[page\s+(\d+)\])\s*$")
_MONEY_TOKEN_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")

_CLAUSE_HEADER_RE = re.compile(
    r"(?im)^(?P<kind>coverage\s*grant|coverage|exclusion|endorsement|sublimit|condition|definition)"
    r"(?:\s*\((?P<section>[^)]+)\))?\s*[:\-–]\s*(?P<title>.+)$"
)
_SECTION_LINE_RE = re.compile(
    r"(?im)^(?P<section>(?:section|sec\.?|article|endorsement|form)\s+[A-Z0-9.\-]+)"
    r"\s*[:\-–]\s*(?P<title>.+)$"
)
_SCHEDULE_LINE_RE = re.compile(
    r"(?im)^(?P<label>schedule|location|vehicle|scheduled\s+item|premises)\s*[:\-]\s*(?P<val>.+)$"
)


def extract_pages_from_bytes(filename: str, data: bytes) -> list[tuple[int, str]]:
    """Extract 1-indexed (page_number, page_text) tuples from PDF, JSON, or TXT bytes."""
    lower = filename.lower()
    if lower.endswith(".pdf") or data.startswith(b"%PDF"):
        reader = PdfReader(io.BytesIO(data))
        pages: list[tuple[int, str]] = []
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            pages.append((idx, text))
        return pages or [(1, "")]

    raw_text = data.decode("utf-8", errors="replace")
    if lower.endswith(".json"):
        try:
            obj = json.loads(raw_text)
            formatted = json.dumps(obj, indent=2)
            return [(1, formatted)]
        except Exception:
            return [(1, raw_text)]

    if "\f" in raw_text:
        parts = [p.strip() for p in raw_text.split("\f")]
        return [(idx, p) for idx, p in enumerate(parts, start=1) if p] or [(1, raw_text)]

    # Split on explicit [Page N] or --- Page N --- markers if present
    lines = raw_text.splitlines()
    current_page = 1
    buckets: dict[int, list[str]] = {1: []}
    for line in lines:
        marker = _PAGE_MARKER_RE.match(line)
        if marker:
            page_str = marker.group(1) or marker.group(2) or str(current_page + 1)
            current_page = max(1, int(page_str))
            buckets.setdefault(current_page, [])
        else:
            buckets.setdefault(current_page, []).append(line)

    pages = [
        (pg, "\n".join(pg_lines).strip())
        for pg, pg_lines in sorted(buckets.items())
        if "\n".join(pg_lines).strip()
    ]
    return pages or [(1, raw_text.strip())]


def _find_field(text: str, patterns: tuple[str, ...], default: str = "") -> str:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            val = m.group(1).strip()
            if val:
                return val
    return default


def _parse_money(text: str, patterns: tuple[str, ...], default: str = "0.00") -> Decimal:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            cleaned = m.group(1).replace(",", "").strip()
            try:
                return quantize_money(cleaned)
            except Exception:
                continue
    return quantize_money(default)


def _infer_lob(raw_lob: str, full_text: str) -> str:
    combined = f"{raw_lob} {full_text[:600]}".lower()
    if "cyber" in combined or "network security" in combined or "ransomware" in combined:
        return "cyber"
    if "general liability" in combined or "cgl" in combined or "acord 125" in combined:
        return "commercial_general_liability"
    if "auto" in combined or "fleet" in combined or "acord 127" in combined:
        return "commercial_auto"
    if "workers" in combined or "wc" in combined:
        return "workers_compensation"
    if "property" in combined or "acord 140" in combined or "building" in combined:
        return "commercial_property"
    return raw_lob.strip().lower().replace(" ", "_") or "commercial_property"


def _classify_clause_kind(raw_kind: str, title: str, body: str) -> str:
    kind_norm = raw_kind.lower().strip()
    combined = f"{kind_norm} {title} {body}".lower()
    if "exclusion" in kind_norm or "excluded" in title.lower() or "exclusion" in title.lower():
        return "exclusion"
    if "endorsement" in kind_norm or "endorsement" in title.lower() or "buy-back" in combined:
        return "endorsement"
    if "sublimit" in kind_norm or "sublimit" in title.lower():
        return "sublimit"
    if "condition" in kind_norm or "notice" in title.lower() or "condition" in title.lower():
        return "condition"
    if "definition" in kind_norm:
        return "definition"
    return "coverage_grant"


def _extract_clause_monetary_terms(text: str) -> tuple[Decimal | None, Decimal | None]:
    limit_match = re.search(
        r"(?i)(?:sublimit|limit\s+of\s+liability|up\s+to|maximum\s+payable|capped\s+at)"
        r"[^$\n]{0,25}\$\s*([\d,]+(?:\.\d{1,2})?)",
        text,
    )
    ded_match = re.search(
        r"(?i)(?:deductible(?:\s+override)?|retention|self-insured\s+retention)"
        r"[^$\n]{0,25}\$\s*([\d,]+(?:\.\d{1,2})?)",
        text,
    )
    limit_val = quantize_money(limit_match.group(1).replace(",", "")) if limit_match else None
    ded_val = quantize_money(ded_match.group(1).replace(",", "")) if ded_match else None
    return limit_val, ded_val


def parse_policy_document(pages: list[tuple[int, str]], filename: str) -> ParsedPolicy:
    """Parse declarations metadata, schedules, and page-indexed clauses from policy pages."""
    combined_pages = [f"[Page {pg}]\n{txt}" for pg, txt in pages if txt.strip()]
    raw_text = "\n\n".join(combined_pages)
    first_pages_text = "\n".join(txt for _, txt in pages[:2]) or raw_text

    today = utcnow().date()
    policy_number = _find_field(
        first_pages_text,
        (
            r"Policy\s*(?:No\.?|Number|#)\s*[:\-]\s*([A-Z0-9\-/]+)",
            r'"policy_number"\s*:\s*"([^"]+)"',
        ),
        default=f"POL-{abs(hash(filename + raw_text[:80])) % 900000 + 100000}",
    )
    carrier_name = _find_field(
        first_pages_text,
        (
            r"Carrier(?:\s*Name)?\s*[:\-]\s*(.+)$",
            r"Insurer\s*[:\-]\s*(.+)$",
            r'"carrier_name"\s*:\s*"([^"]+)"',
        ),
        default="ShieldGuard Commercial Insurance Co.",
    )
    named_insured = _find_field(
        first_pages_text,
        (
            r"Named\s+Insured\s*[:\-]\s*(.+)$",
            r"Insured(?:\s+Name)?\s*[:\-]\s*(.+)$",
            r'"named_insured"\s*:\s*"([^"]+)"',
        ),
        default="Unnamed Commercial Insured",
    )
    insured_address = _find_field(
        first_pages_text,
        (
            r"(?:Mailing|Insured|Premises)\s+Address\s*[:\-]\s*(.+)$",
            r'"insured_address"\s*:\s*"([^"]+)"',
        ),
        default="",
    )
    raw_lob = _find_field(
        first_pages_text,
        (
            r"Line\s+of\s+Business\s*[:\-]\s*(.+)$",
            r"Coverage\s+Line\s*[:\-]\s*(.+)$",
            r'"line_of_business"\s*:\s*"([^"]+)"',
        ),
        default="Commercial Property",
    )
    acord_form_type = _find_field(
        first_pages_text,
        (
            r"(ACORD\s+\d+[A-Z]?)",
            r"Form\s*[:\-]\s*(ACORD\s+\d+[A-Z]?)",
        ),
        default="ACORD 140",
    )
    eff_raw = _find_field(
        first_pages_text,
        (
            r"Effective\s+Date\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
            r"Policy\s+Period\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        ),
    )
    exp_raw = _find_field(
        first_pages_text,
        (
            r"Expiration\s+Date\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
            r"Policy\s+Period\s*[:\-]\s*[0-9]{4}-[0-9]{2}-[0-9]{2}\s*(?:to|-|through)\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        ),
    )
    effective_date = parse_iso_date(eff_raw, fallback=today)
    expiration_date = parse_iso_date(exp_raw, fallback=effective_date + timedelta(days=365))

    per_occurrence_limit = _parse_money(
        first_pages_text,
        (
            r"(?:Per\s+Occurrence|Each\s+Occurrence|Building|Policy)\s+Limit\s*[:\-]\s*\$?\s*([\d,]+(?:\.\d{1,2})?)",
            r'"per_occurrence_limit"\s*:\s*([\d.]+)',
        ),
        default="1000000.00",
    )
    aggregate_limit = _parse_money(
        first_pages_text,
        (
            r"(?:General\s+)?Aggregate\s+Limit\s*[:\-]\s*\$?\s*([\d,]+(?:\.\d{1,2})?)",
            r'"aggregate_limit"\s*:\s*([\d.]+)',
        ),
        default=str(per_occurrence_limit * 2),
    )
    deductible = _parse_money(
        first_pages_text,
        (
            r"(?:All\s+Other\s+Perils\s+)?Deductible\s*[:\-]\s*\$?\s*([\d,]+(?:\.\d{1,2})?)",
            r'"deductible"\s*:\s*([\d.]+)',
        ),
        default="5000.00",
    )
    annual_premium = _parse_money(
        first_pages_text,
        (
            r"(?:Annual\s+|Total\s+)?Premium\s*[:\-]\s*\$?\s*([\d,]+(?:\.\d{1,2})?)",
            r'"annual_premium"\s*:\s*([\d.]+)',
        ),
        default="24000.00",
    )

    schedules: list[dict[str, Any]] = []
    clauses: list[ParsedClause] = []

    for page_num, page_text in pages:
        lines = page_text.splitlines()
        current_clause: dict[str, str] | None = None
        body_lines: list[str] = []

        def _flush_clause(pg: int, hdr: dict[str, str] | None, body: list[str]) -> None:
            if hdr is None:
                return
            text_body = " ".join(part.strip() for part in body if part.strip()).strip()
            if not text_body:
                text_body = hdr["title"]
            ctype = _classify_clause_kind(hdr["kind"], hdr["title"], text_body)
            lim, ded = _extract_clause_monetary_terms(f"{hdr['title']} {text_body}")
            clauses.append(
                ParsedClause(
                    clause_type=ctype,
                    section_ref=hdr["section"],
                    page_number=pg,
                    title=hdr["title"][:240],
                    clause_text=text_body,
                    monetary_limit=lim,
                    deductible_override=ded,
                    keywords=extract_keywords(f"{hdr['title']} {text_body}"),
                )
            )

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            sched_match = _SCHEDULE_LINE_RE.match(line)
            if sched_match:
                money_hits = _MONEY_TOKEN_RE.findall(line)
                schedules.append(
                    {
                        "category": sched_match.group("label").lower(),
                        "description": sched_match.group("val").strip(),
                        "page_number": page_num,
                        "scheduled_value": (
                            float(money_hits[0].replace(",", "")) if money_hits else None
                        ),
                    }
                )

            c_match = _CLAUSE_HEADER_RE.match(line)
            s_match = _SECTION_LINE_RE.match(line) if not c_match else None
            if c_match:
                _flush_clause(page_num, current_clause, body_lines)
                current_clause = {
                    "kind": c_match.group("kind").strip(),
                    "section": (c_match.group("section") or f"Page {page_num} Sec").strip(),
                    "title": c_match.group("title").strip(),
                }
                body_lines = []
            elif s_match:
                _flush_clause(page_num, current_clause, body_lines)
                current_clause = {
                    "kind": "coverage_grant",
                    "section": s_match.group("section").strip(),
                    "title": s_match.group("title").strip(),
                }
                body_lines = []
            elif current_clause is not None:
                body_lines.append(line)

        _flush_clause(page_num, current_clause, body_lines)

    if not clauses and raw_text.strip():
        clauses.append(
            ParsedClause(
                clause_type="coverage_grant",
                section_ref="Declarations Page 1",
                page_number=1,
                title=f"Insuring Agreement — {named_insured}",
                clause_text=raw_text[:2000],
                monetary_limit=per_occurrence_limit,
                deductible_override=deductible,
                keywords=extract_keywords(raw_text),
            )
        )

    confidence = 0.72
    if named_insured != "Unnamed Commercial Insured":
        confidence += 0.1
    if eff_raw and exp_raw:
        confidence += 0.08
    if len(clauses) >= 2:
        confidence += 0.07

    return ParsedPolicy(
        policy_number=policy_number,
        carrier_name=carrier_name[:200],
        named_insured=named_insured[:240],
        insured_address=insured_address[:320],
        line_of_business=_infer_lob(raw_lob, raw_text),
        acord_form_type=acord_form_type[:80],
        effective_date=effective_date,
        expiration_date=expiration_date,
        status="active",
        per_occurrence_limit=per_occurrence_limit,
        aggregate_limit=aggregate_limit,
        deductible=deductible,
        annual_premium=annual_premium,
        raw_text=raw_text,
        schedules=schedules,
        clauses=clauses,
        extraction_confidence=round(min(0.99, confidence), 2),
    )
