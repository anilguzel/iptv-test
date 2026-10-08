from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bist_core.schemas import Tick


def make_ticks(prices: list[float], volumes: list[float], *, end: datetime | None = None, step_min: int = 1) -> list[Tick]:
    """Build a 1-min-spaced tick series ending at `end` (default: now, UTC)."""
    assert len(prices) == len(volumes)
    end = end or datetime.now(UTC)
    n = len(prices)
    return [
        Tick(timestamp=end - timedelta(minutes=step_min * (n - 1 - i)), price=prices[i], volume=volumes[i])
        for i in range(n)
    ]
