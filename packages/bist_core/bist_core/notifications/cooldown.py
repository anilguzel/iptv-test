"""Alert cooldown / de-duplication (spec section 20).

Pure, in-memory and fully testable. A signal reversal bypasses the cooldown and
is always sent immediately; everything else is throttled per symbol and must
move by at least ``min_score_delta`` points since the last sent alert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..enums import SignalChange


@dataclass
class _Last:
    at: datetime
    score: float


@dataclass
class AlertCooldown:
    cooldown_seconds: int = 600
    reversal_cooldown_seconds: int = 0
    min_score_delta: float = 10.0
    _last: dict[str, _Last] = field(default_factory=dict)

    def should_send(
        self,
        symbol: str,
        *,
        score: float,
        change: SignalChange,
        now: datetime | None = None,
    ) -> bool:
        now = now or datetime.now(UTC)
        last = self._last.get(symbol)
        is_reversal = change == SignalChange.REVERSAL

        if last is None:
            self._record(symbol, score, now)
            return True

        elapsed = (now - last.at).total_seconds()
        cooldown = self.reversal_cooldown_seconds if is_reversal else self.cooldown_seconds

        if elapsed < cooldown:
            return False
        if not is_reversal and abs(score - last.score) < self.min_score_delta:
            return False

        self._record(symbol, score, now)
        return True

    def _record(self, symbol: str, score: float, at: datetime) -> None:
        self._last[symbol] = _Last(at=at, score=score)
