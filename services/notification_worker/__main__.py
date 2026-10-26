"""Notification worker.

Watches for newly persisted signals and sends Telegram alerts for meaningful
changes, applying the per-symbol cooldown (reversals bypass it). Alerts are
recorded in the ``alerts`` table; a missing/disabled Telegram config degrades
to logging only.
"""
from __future__ import annotations

import asyncio
import logging

from bist_core.config import get_settings
from bist_core.db import init_db, models, session_scope
from bist_core.enums import SignalChange
from bist_core.notifications import AlertCooldown, TelegramNotifier, format_alert
from bist_core.schemas import SignalPayload
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("notification_worker")

# Only these changes are worth an alert.
ALERTABLE = {"SIGNAL_STRENGTHENING", "SIGNAL_WEAKENING", "SIGNAL_REVERSAL"}


async def main() -> None:
    settings = get_settings()
    init_db()
    notifier = TelegramNotifier(settings)
    cooldown = AlertCooldown(
        cooldown_seconds=settings.alert_cooldown_seconds,
        reversal_cooldown_seconds=settings.reversal_cooldown_seconds,
        min_score_delta=settings.alert_min_score_delta,
    )
    last_seen_id = 0
    log.info("notification-worker started (telegram_enabled=%s)", notifier.enabled)

    while True:
        with session_scope() as session:
            rows = session.scalars(
                select(models.Signal)
                .where(models.Signal.id > last_seen_id, models.Signal.change.in_(ALERTABLE))
                .order_by(models.Signal.id.asc())
                .limit(50)
            ).all()
            for sig in rows:
                last_seen_id = max(last_seen_id, sig.id)
                change = SignalChange(sig.change)
                if not cooldown.should_send(sig.symbol, score=sig.score, change=change):
                    continue
                snap = sig.data_snapshot or {}
                payload = SignalPayload(
                    symbol=sig.symbol,
                    timestamp=sig.timestamp,
                    score=sig.score,
                    direction=sig.direction,
                    confidence=sig.confidence,
                    change=change,
                    evidence=sig.evidence or [],
                    risks=sig.risks or [],
                    invalidation_conditions=sig.invalidation_conditions or [],
                    data_status=sig.data_status,
                    data_snapshot=snap,
                )
                title, body = format_alert(
                    payload,
                    price=snap.get("price", 0.0),
                    change_percent=snap.get("change_percent"),
                    volume_ratio=(snap.get("volume") or {}).get("volume_ratio_5m"),
                )
                delivered = await notifier.send(body)
                session.add(
                    models.Alert(
                        symbol=sig.symbol,
                        channel="telegram",
                        title=title,
                        body=body,
                        signal_id=sig.id,
                        delivered=delivered,
                    )
                )
                log.info("alert %s %s delivered=%s", sig.symbol, sig.change, delivered)
        await asyncio.sleep(max(settings.signal_interval_seconds // 2, 5))


if __name__ == "__main__":
    asyncio.run(main())
