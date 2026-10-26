"""Rolling flow engine (proxy flow — NOT institutional AKD).

The free provider gives price + cumulative volume only. We therefore derive a
*signed money-flow proxy* per tick:

    contribution = delta_volume * price * sign(delta_price)

and roll it over 1/5/15/30/60 minute windows plus the full session. We also
compute momentum and acceleration (current window vs the immediately preceding
equal-length window), which is the heart of the "cumulative analysis" module.

These are explicitly proxies. See README "Known limitations".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from ..schemas import FlowMetrics, Tick


@dataclass
class _Contribution:
    ts: datetime
    signed_flow: float
    delta_volume: float
    ret: float  # fractional price return over the interval


def _sign(x: float) -> float:
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


def _contributions(ticks: list[Tick]) -> list[_Contribution]:
    out: list[_Contribution] = []
    for prev, cur in pairwise(ticks):
        # Cumulative session volume is non-decreasing; guard against resets.
        dv = cur.volume - prev.volume
        if dv < 0:
            dv = cur.volume  # session reset -> treat current as the increment
        dp = cur.price - prev.price
        ret = (dp / prev.price) if prev.price else 0.0
        out.append(
            _Contribution(
                ts=cur.timestamp,
                signed_flow=dv * cur.price * _sign(dp),
                delta_volume=max(dv, 0.0),
                ret=ret,
            )
        )
    return out


def _window(contribs: list[_Contribution], end: datetime, start_min: float, end_min: float) -> list[_Contribution]:
    """Contributions with timestamp in (end - start_min, end - end_min]."""
    lo = end - timedelta(minutes=start_min)
    hi = end - timedelta(minutes=end_min)
    return [c for c in contribs if lo < c.ts <= hi]


class FlowEngine:
    def compute(self, ticks: list[Tick]) -> FlowMetrics:
        ticks = sorted(ticks, key=lambda t: t.timestamp)
        if len(ticks) < 2:
            return FlowMetrics()
        contribs = _contributions(ticks)
        now = ticks[-1].timestamp

        def flow(minutes: float) -> float:
            return sum(c.signed_flow for c in _window(contribs, now, minutes, 0))

        def vol(minutes: float, offset: float = 0.0) -> float:
            return sum(c.delta_volume for c in _window(contribs, now, minutes + offset, offset))

        def ret(minutes: float, offset: float = 0.0) -> float:
            return sum(c.ret for c in _window(contribs, now, minutes + offset, offset))

        flow_15_cur = flow(15)
        flow_15_prev = sum(c.signed_flow for c in _window(contribs, now, 30, 15))

        return FlowMetrics(
            flow_1m=flow(1),
            flow_5m=flow(5),
            flow_15m=flow_15_cur,
            flow_30m=flow(30),
            flow_60m=flow(60),
            flow_day=sum(c.signed_flow for c in contribs),
            price_momentum=ret(5),
            volume_momentum=vol(5),
            price_acceleration=ret(5) - ret(5, offset=5),
            volume_acceleration=vol(5) - vol(5, offset=5),
            flow_acceleration=flow_15_cur - flow_15_prev,
        )
