"""
Simple rate setter for previous-day close prices.

No real-time feeds, no CoinGecko, no websockets. Just record
yesterday's close price and use it for conversions today.
Rates are stored in the ledger's append-only rates.jsonl.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..core.models import ExchangeRate
from ..storage.base import StorageBackend


class RateSetter:
    """Set and retrieve previous-day close prices."""

    def __init__(self, store: StorageBackend):
        self.store = store

    def set_rate(self, from_currency: str, to_currency: str,
                 rate: Decimal, source: str = "manual") -> ExchangeRate:
        """
        Record a closing price.

        Example: set_rate("XAG", "USD", Decimal("29.50"), "kitco")
        means 1 troy oz silver = $29.50 at close.
        """
        record = ExchangeRate(
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
            source=source,
        )
        return self.store.record_rate(record)

    def get_rate(self, from_currency: str,
                 to_currency: str) -> Optional[Decimal]:
        """Get the most recent rate for a currency pair."""
        record = self.store.get_latest_rate(from_currency, to_currency)
        return record.rate if record else None

    def convert(self, amount: Decimal, from_currency: str,
                to_currency: str) -> Optional[Decimal]:
        """Convert an amount using the latest recorded rate."""
        if from_currency == to_currency:
            return amount
        rate = self.get_rate(from_currency, to_currency)
        if rate is None:
            return None
        return amount * rate

    def set_daily_closes(self, closes: dict[str, Decimal],
                         source: str = "manual") -> list[ExchangeRate]:
        """
        Batch-set daily close prices vs USD.

        closes = {"XAG": Decimal("29.50"), "BTC": Decimal("67000"), ...}
        """
        results = []
        for currency, rate_to_usd in closes.items():
            results.append(self.set_rate(currency, "USD", rate_to_usd, source))
            # Also store the inverse
            if rate_to_usd > 0:
                inverse = Decimal("1") / rate_to_usd
                results.append(self.set_rate("USD", currency, inverse, source))
        return results
