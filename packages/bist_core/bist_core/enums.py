"""Shared enumerations for the BIST Intelligence platform.

These values are stable contracts shared across the API, signal engine,
notification worker and frontend. Keep the string values stable.
"""
from __future__ import annotations

from enum import Enum


class SignalDirection(str, Enum):
    """Qualitative label derived from the deterministic flow score.

    IMPORTANT: this is *strength of current evidence*, never a probability
    of the price rising. See ``score_to_direction``.
    """

    STRONG_NEGATIVE = "STRONG_NEGATIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    POSITIVE = "POSITIVE"
    STRONG_POSITIVE = "STRONG_POSITIVE"
    EXTREME_POSITIVE = "EXTREME_POSITIVE"
    WATCH = "WATCH"


class DataStatus(str, Enum):
    """Freshness / provenance of a quote.

    The initial free provider is always ``DELAYED`` (~15 min). ``LIVE`` must
    only ever be used when a provider explicitly reports real-time data.
    """

    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    DEMO = "DEMO"


class SignalChange(str, Enum):
    STRENGTHENING = "SIGNAL_STRENGTHENING"
    WEAKENING = "SIGNAL_WEAKENING"
    REVERSAL = "SIGNAL_REVERSAL"
    STABLE = "SIGNAL_STABLE"


class AnomalyType(str, Enum):
    VOLUME_SPIKE = "VOLUME_SPIKE"
    VOLUME_ACCELERATION = "VOLUME_ACCELERATION"
    VOLUME_DIVERGENCE = "VOLUME_DIVERGENCE"
    PRICE_SPIKE = "PRICE_SPIKE"
    PRICE_DROP = "PRICE_DROP"
    FLOW_ACCELERATION = "FLOW_ACCELERATION"
    BREAKOUT = "BREAKOUT"
    BREAKDOWN = "BREAKDOWN"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    PRICE_VOLUME_DIVERGENCE = "PRICE_VOLUME_DIVERGENCE"
    NEW_INTRADAY_HIGH = "NEW_INTRADAY_HIGH"
    NEW_INTRADAY_LOW = "NEW_INTRADAY_LOW"
    UNUSUAL_ACTIVITY = "UNUSUAL_ACTIVITY"


class AnomalySeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NewsCategory(str, Enum):
    FINANCIAL = "FINANCIAL"
    CONTRACT = "CONTRACT"
    TENDER = "TENDER"
    ACQUISITION = "ACQUISITION"
    MERGER = "MERGER"
    PARTNERSHIP = "PARTNERSHIP"
    CAPITAL = "CAPITAL"
    SHARE_TRANSACTION = "SHARE_TRANSACTION"
    MANAGEMENT = "MANAGEMENT"
    REGULATORY = "REGULATORY"
    OTHER = "OTHER"
