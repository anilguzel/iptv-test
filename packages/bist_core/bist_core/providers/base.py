"""Provider interfaces.

The application depends on these abstractions, never on a concrete provider,
so the data source can be swapped (or upgraded to a real-time / AKD provider)
without touching the engines, API or UI.
"""
from __future__ import annotations

import abc
from datetime import datetime

from ..schemas import IntradayPoint, NewsEvent, OhlcvBar, Quote


class MarketDataProvider(abc.ABC):
    """Normalised market-data source.

    Implementations MUST preserve the true freshness of their data via
    ``Quote.data_status`` and MUST NOT report LIVE unless the upstream source
    is genuinely real-time.
    """

    name: str = "abstract"
    #: Whether this provider's data is real-time. The free BIST service is not.
    realtime: bool = False

    @abc.abstractmethod
    async def get_quote(self, symbol: str) -> Quote: ...

    @abc.abstractmethod
    async def get_quotes(self, symbols: list[str]) -> list[Quote]: ...

    @abc.abstractmethod
    async def get_history(
        self, symbol: str, *, interval: str = "1d", limit: int = 120
    ) -> list[OhlcvBar]: ...

    @abc.abstractmethod
    async def get_intraday(self, symbol: str) -> list[IntradayPoint]: ...

    async def aclose(self) -> None:  # pragma: no cover - optional lifecycle hook
        """Release any held resources (HTTP clients, etc.)."""


class NewsProvider(abc.ABC):
    """Compliant news / KAP adapter.

    The MVP ships only a mock implementation. A licensed KAP/news provider can
    be dropped in later without changing the news→price correlation logic.
    """

    name: str = "abstract"

    @abc.abstractmethod
    async def get_news(
        self, symbol: str, *, since: datetime | None = None
    ) -> list[NewsEvent]: ...


# --------------------------------------------------------------------------- #
# Future provider interfaces.                                                 #
#                                                                             #
# These are fully typed but intentionally UNIMPLEMENTED. They mark the exact  #
# seam where a licensed real-time provider (Matriks, Foreks, ...) can supply  #
# institutional flow (AKD), Level-2 order book, and raw trades.               #
#                                                                             #
# We deliberately ship NO fake AKD data — see README "Known limitations".     #
# --------------------------------------------------------------------------- #
class InstitutionFlowProvider(abc.ABC):
    """Institutional (brokerage-attributed) net flow — AKD. NOT YET AVAILABLE."""

    name: str = "abstract"

    @abc.abstractmethod
    async def get_institution_flow(self, symbol: str) -> object: ...  # pragma: no cover


class OrderBookProvider(abc.ABC):
    """Level-2 order book depth. NOT YET AVAILABLE from the free provider."""

    name: str = "abstract"

    @abc.abstractmethod
    async def get_order_book(self, symbol: str, *, depth: int = 10) -> object: ...  # pragma: no cover


class TradeProvider(abc.ABC):
    """Raw time-and-sales trade stream. NOT YET AVAILABLE from the free provider."""

    name: str = "abstract"

    @abc.abstractmethod
    async def get_trades(self, symbol: str, *, limit: int = 100) -> object: ...  # pragma: no cover
