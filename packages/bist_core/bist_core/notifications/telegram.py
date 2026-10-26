"""Telegram alert formatting and delivery."""
from __future__ import annotations

import httpx

from ..config import Settings, get_settings
from ..schemas import SignalPayload


def format_alert(signal: SignalPayload, *, price: float, change_percent: float | None, volume_ratio: float | None) -> tuple[str, str]:
    """Return (title, body) for an alert message."""
    title = f"{signal.symbol} — {signal.direction.value}"
    lines = [
        f"\U0001F4CA {signal.symbol} — {signal.direction.value}",
        f"Price: {price} ({change_percent:+.2f}%)" if change_percent is not None else f"Price: {price}",
    ]
    if volume_ratio is not None:
        lines.append(f"Volume: {volume_ratio:.1f}x baseline")
    lines.append(f"Flow Score: {signal.score:.0f}/100 (evidence strength, not probability)")
    lines.append(f"Change: {signal.change.value}")
    lines.append(f"Confidence: {signal.confidence:.0%} | Data: {signal.data_status.value}")
    if signal.evidence:
        lines.append("Reasons: " + "; ".join(f"• {e}" for e in signal.evidence[:4]))
    if signal.risks:
        lines.append("Risks: " + "; ".join(f"• {r}" for r in signal.risks[:3]))
    if signal.invalidation_conditions:
        lines.append("Invalidation: " + "; ".join(f"• {i}" for i in signal.invalidation_conditions[:3]))
    return title, "\n".join(lines)


class TelegramNotifier:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.telegram_enabled
            and self.settings.telegram_bot_token
            and self.settings.telegram_chat_id
        )

    async def send(self, body: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"chat_id": self.settings.telegram_chat_id, "text": body})
            return resp.status_code == 200
