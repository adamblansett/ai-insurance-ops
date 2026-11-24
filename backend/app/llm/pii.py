import re
from dataclasses import dataclass

from pydantic import BaseModel


class RedactionFinding(BaseModel):
    """Summary count of redacted PII/PHI tokens by category."""

    category: str
    count: int
    placeholder: str


class RedactionResult(BaseModel):
    """Result returned by PII/PHI scrubbing before outbound cloud inference."""

    redacted_text: str
    findings: list[RedactionFinding]
    total_redactions: int


@dataclass(frozen=True)
class _PatternRule:
    category: str
    placeholder: str
    pattern: re.Pattern[str]


_RULES: tuple[_PatternRule, ...] = (
    _PatternRule(
        category="ssn",
        placeholder="[REDACTED_SSN]",
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    _PatternRule(
        category="fein",
        placeholder="[REDACTED_FEIN]",
        pattern=re.compile(r"\b\d{2}-\d{7}\b"),
    ),
    _PatternRule(
        category="email",
        placeholder="[REDACTED_EMAIL]",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    _PatternRule(
        category="dob",
        placeholder="[REDACTED_DOB]",
        pattern=re.compile(
            r"(?i)\b(?:dob|date\s+of\s+birth|birth\s*date|born)\s*[:=#-]?\s*"
            r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b"
        ),
    ),
    _PatternRule(
        category="drivers_license",
        placeholder="[REDACTED_DL]",
        pattern=re.compile(
            r"(?i)\b(?:dl|driver'?s?\s*license|license\s*(?:no|num|number|#)?)"
            r"\s*[:=#-]?\s*[A-Z0-9-]{6,16}\b"
        ),
    ),
    _PatternRule(
        category="vin",
        placeholder="[REDACTED_VIN]",
        pattern=re.compile(
            r"(?i)\b(?:vin\s*[:=#-]?\s*[A-HJ-NPR-Z0-9]{17}|"
            r"[A-HJ-NPR-Z0-9]{11}\d{6})\b"
        ),
    ),
    _PatternRule(
        category="member_id",
        placeholder="[REDACTED_MEMBER_ID]",
        pattern=re.compile(
            r"(?i)\b(?:member|subscriber|claimant)\s*(?:id|no|num|number|#)"
            r"\s*[:=#-]?\s*[A-Z0-9-]{5,20}\b"
        ),
    ),
    _PatternRule(
        category="phone",
        placeholder="[REDACTED_PHONE]",
        pattern=re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b"),
    ),
)

_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    total = 0
    reverse_digits = digits[::-1]
    for idx, ch in enumerate(reverse_digits):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def redact_pii(text: str) -> RedactionResult:
    """Scrub sensitive insurance PII/PHI fields before outbound cloud LLM inference."""
    if not text:
        return RedactionResult(redacted_text="", findings=[], total_redactions=0)

    working = text
    counts: dict[tuple[str, str], int] = {}

    for rule in _RULES:
        working, n = rule.pattern.subn(rule.placeholder, working)
        if n > 0:
            key = (rule.category, rule.placeholder)
            counts[key] = counts.get(key, 0) + n

    card_count = 0

    def _replace_card(match: re.Match[str]) -> str:
        nonlocal card_count
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if _luhn_valid(digits):
            card_count += 1
            return "[REDACTED_CARD]"
        return raw

    working = _CARD_CANDIDATE_RE.sub(_replace_card, working)
    if card_count > 0:
        key = ("payment_card", "[REDACTED_CARD]")
        counts[key] = counts.get(key, 0) + card_count

    findings = [
        RedactionFinding(category=cat, count=cnt, placeholder=ph)
        for (cat, ph), cnt in counts.items()
    ]
    total = sum(f.count for f in findings)
    return RedactionResult(
        redacted_text=working,
        findings=findings,
        total_redactions=total,
    )
