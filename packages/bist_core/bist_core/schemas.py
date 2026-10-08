"""Pydantic DTOs shared across providers, engines, the API and workers.

These are transport/compute objects (not ORM rows). Engines operate on these
pure dataclass-like models so they can be unit-tested with deterministic
fixtures and never need a database.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AnomalySeverity,
    AnomalyType,
    DataStatus,
    NewsCategory,
    SignalChange,
    SignalDirection,
)


class Quote(BaseModel):
    """A normalised market quote as returned by a MarketDataProvider.

    The provider contract preserves delay/freshness via ``data_status`` and
    ``latency`` so the UI can never falsely claim LIVE data.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    price: float
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float = 0.0
    # Timestamp reported by the market/provider for this quote.
    timestamp: datetime
    data_status: DataStatus = DataStatus.DELAYED
    provider: str = "unknown"
    # Round-trip latency to the provider, seconds.
    latency: float | None = None


class OhlcvBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class IntradayPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    price: float
    volume: float


class Tick(BaseModel):
    """A single ingested observation used by the flow/volume engines."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    price: float
    # Cumulative session volume reported by the provider at this timestamp.
    volume: float


class FlowMetrics(BaseModel):
    """Rolling signed-flow proxies and acceleration derived from ticks.

    We do NOT have institutional AKD / order-book data from the free provider,
    so these are explicitly *proxies* computed from price & volume deltas.
    """

    flow_1m: float = 0.0
    flow_5m: float = 0.0
    flow_15m: float = 0.0
    flow_30m: float = 0.0
    flow_60m: float = 0.0
    flow_day: float = 0.0

    price_momentum: float = 0.0
    volume_momentum: float = 0.0
    price_acceleration: float = 0.0
    volume_acceleration: float = 0.0
    flow_acceleration: float = 0.0


class VolumeMetrics(BaseModel):
    volume_ratio_5m: float = 1.0
    volume_ratio_15m: float = 1.0
    volume_ratio_day: float = 1.0
    volume_5m: float = 0.0
    volume_15m: float = 0.0


class TechnicalMetrics(BaseModel):
    ema_9: float | None = None
    sma_20: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    vwap: float | None = None


class Anomaly(BaseModel):
    type: AnomalyType
    severity: AnomalySeverity
    timestamp: datetime
    symbol: str
    evidence: str
    threshold: float | None = None
    observed: float | None = None


class NewsEvent(BaseModel):
    symbol: str
    timestamp: datetime
    headline: str
    category: NewsCategory = NewsCategory.OTHER
    importance: int = 1  # 1 (low) .. 5 (critical)
    source: str = "mock"


class ScoreComponent(BaseModel):
    name: str
    raw: float  # normalised 0..1 contribution of this component
    weight: float
    points: float  # raw * weight


class ScoreResult(BaseModel):
    """The deterministic flow score plus a full, reconstructable breakdown."""

    score: float
    direction: SignalDirection
    confidence: float  # 0..1, downgraded for stale/thin data
    components: list[ScoreComponent]
    scoring_version: str
    # The exact inputs used so the signal can be reconstructed later.
    data_snapshot: dict = Field(default_factory=dict)


class SignalPayload(BaseModel):
    """What gets persisted to the ``signals`` table and sent downstream."""

    symbol: str
    timestamp: datetime
    score: float
    direction: SignalDirection
    confidence: float
    change: SignalChange = SignalChange.STABLE
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    data_status: DataStatus = DataStatus.DELAYED
    data_snapshot: dict = Field(default_factory=dict)


class AIAnalysis(BaseModel):
    summary: str
    key_moves: list[str] = Field(default_factory=list)
    buying_pressure: list[str] = Field(default_factory=list)
    selling_pressure: list[str] = Field(default_factory=list)
    momentum: str = ""
    news_context: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    signal: str = ""
    confidence: float = 0.0
    invalidation_conditions: list[str] = Field(default_factory=list)
    next_trigger: str = ""
