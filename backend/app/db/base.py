from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def new_uuid() -> str:
    """Return a new string UUID."""
    return str(uuid4())


def quantize_money(value: Decimal | float | int | str) -> Decimal:
    """Round any numeric money value cleanly to 2 decimal places."""
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_iso_date(value: date | datetime | str | None, fallback: date | None = None) -> date:
    """Parse an ISO-8601 date/datetime string safely."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            try:
                return date.fromisoformat(cleaned[:10])
            except ValueError:
                pass
    return fallback or datetime.now(UTC).date()
