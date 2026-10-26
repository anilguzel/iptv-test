"""Inbound data validation. Never blindly trust provider values."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .schemas import Quote


class ValidationError(ValueError):
    pass


def validate_quote(quote: Quote, *, known_symbols: set[str] | None = None) -> Quote:
    """Validate a quote, raising ValidationError on anything implausible."""
    if quote.price <= 0:
        raise ValidationError(f"{quote.symbol}: price must be > 0 (got {quote.price})")
    if quote.volume < 0:
        raise ValidationError(f"{quote.symbol}: volume must be >= 0 (got {quote.volume})")
    if not quote.symbol or not quote.symbol.isalnum():
        raise ValidationError(f"invalid symbol {quote.symbol!r}")
    if known_symbols is not None and quote.symbol.upper() not in known_symbols:
        raise ValidationError(f"unknown symbol {quote.symbol!r}")

    ts = quote.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    # Reject timestamps implausibly far in the future (clock skew / bad data).
    if ts > now + timedelta(minutes=5):
        raise ValidationError(f"{quote.symbol}: timestamp in the future ({ts.isoformat()})")
    return quote
