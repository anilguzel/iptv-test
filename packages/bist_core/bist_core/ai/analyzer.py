"""AI analyzer.

The deterministic engines compute the score; the AI only *explains* it. The
analyzer receives structured JSON and must return strict JSON matching
:class:`AIAnalysis`. It never invents calculations or market data.

Two implementations:
  * ``MockAIAnalyzer``  - deterministic, offline, derives prose from the score
    breakdown. Default so the app runs with no API key.
  * ``AnthropicAIAnalyzer`` - calls the Claude API when ``AI_PROVIDER=anthropic``
    and a key is present; falls back to the mock on any error.
"""
from __future__ import annotations

import json

from ..config import Settings, get_settings
from ..schemas import AIAnalysis, ScoreResult


def _snapshot_for_ai(symbol: str, price: float, score: ScoreResult, news: list[str]) -> dict:
    snap = score.data_snapshot
    return {
        "symbol": symbol,
        "price": price,
        "change_percent": snap.get("change_percent"),
        "flow": snap.get("flow"),
        "volume": snap.get("volume"),
        "technical": snap.get("technical"),
        "score": score.score,
        "direction": score.direction.value,
        "confidence": score.confidence,
        "component_norms": snap.get("component_norms"),
        "data_status": snap.get("data_status"),
        "news_events": news,
    }


class MockAIAnalyzer:
    name = "mock"

    def analyze(self, *, symbol: str, price: float, score: ScoreResult, news: list[str] | None = None) -> AIAnalysis:
        news = news or []
        snap = score.data_snapshot
        flow = snap.get("flow", {})
        vol = snap.get("volume", {})
        norms = snap.get("component_norms", {})

        buying, selling = [], []
        for name, raw in norms.items():
            label = name.replace("_", " ")
            if raw > 0.55:
                buying.append(f"{label} supportive ({raw:.2f})")
            elif raw < 0.45:
                selling.append(f"{label} weak ({raw:.2f})")

        momentum = "accelerating" if flow.get("flow_acceleration", 0) > 0 else "flat/decelerating"
        vr = vol.get("volume_ratio_5m", 1.0)
        return AIAnalysis(
            summary=(
                f"{symbol}: flow score {score.score}/100 ({score.direction.value}). "
                f"This reflects current evidence strength, not a probability. "
                f"Data is {snap.get('data_status')}."
            ),
            key_moves=[f"5m volume {vr:.1f}x baseline", f"price momentum {flow.get('price_momentum', 0)*100:.2f}% / 5m"],
            buying_pressure=buying or ["none notable"],
            selling_pressure=selling or ["none notable"],
            momentum=momentum,
            news_context=news or ["Mevcut veri kaynaklarında yeni haber tespit edilmedi."],
            risks=[
                "delayed market data" if snap.get("data_status") == "DELAYED" else "data quality",
                "no confirmed institutional (AKD) context",
            ],
            signal=score.direction.value,
            confidence=score.confidence,
            invalidation_conditions=["score below 60", "momentum reversal"] if score.score >= 60 else ["score above 40 on reversal"],
            next_trigger="sustained volume acceleration with price confirmation",
        )


_SYSTEM_PROMPT = (
    "You are a BIST market-data explainer. You receive a deterministic signal "
    "and structured metrics. NEVER recompute or invent numbers or market data. "
    "Explain the provided score only. Clearly treat the score as evidence "
    "strength, not a probability. Respond with STRICT JSON matching the schema "
    "keys: summary, key_moves[], buying_pressure[], selling_pressure[], momentum, "
    "news_context[], risks[], signal, confidence, invalidation_conditions[], next_trigger. "
    "If you cannot analyze, return {\"summary\": \"data_unavailable\"}."
)


class AnthropicAIAnalyzer:
    name = "anthropic"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._fallback = MockAIAnalyzer()

    def analyze(self, *, symbol: str, price: float, score: ScoreResult, news: list[str] | None = None) -> AIAnalysis:
        try:
            import anthropic  # imported lazily so the dep is optional
        except ImportError:
            return self._fallback.analyze(symbol=symbol, price=price, score=score, news=news)
        if not self.settings.anthropic_api_key:
            return self._fallback.analyze(symbol=symbol, price=price, score=score, news=news)

        try:
            client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
            payload = _snapshot_for_ai(symbol, price, score, news or [])
            msg = client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=800,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            text = "".join(block.text for block in msg.content if getattr(block, "type", None) == "text")
            data = json.loads(text)
            if data.get("summary") == "data_unavailable":
                return self._fallback.analyze(symbol=symbol, price=price, score=score, news=news)
            data.setdefault("confidence", score.confidence)
            data.setdefault("signal", score.direction.value)
            return AIAnalysis(**data)
        except Exception:
            return self._fallback.analyze(symbol=symbol, price=price, score=score, news=news)


def get_ai_analyzer(settings: Settings | None = None):
    settings = settings or get_settings()
    if settings.ai_provider.lower() == "anthropic":
        return AnthropicAIAnalyzer(settings)
    return MockAIAnalyzer()
