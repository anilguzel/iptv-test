"""BIST Intelligence core library.

Provider adapters, deterministic engines (flow / volume / scoring / anomaly /
signal-change / backtest), AI explainer, persistence and the signal pipeline.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .config import Settings, get_settings
from .pipeline import SignalPipeline

__all__ = ["Settings", "SignalPipeline", "__version__", "get_settings"]
