"""
Currency registry.

Manages available currencies and provides formatting utilities.
Default currencies (USD, XAG, MERIT, BTC, ETH) are registered
on initialization.
"""

from typing import Optional

from .models import Currency, CURRENCIES
from ..storage.base import StorageBackend


class CurrencyRegistry:
    """Manages currencies in the accounting system."""

    def __init__(self, store: StorageBackend):
        self.store = store

    def initialize_defaults(self):
        """Register all default currencies if not already present."""
        for currency in CURRENCIES.values():
            if not self.store.get_currency(currency.code):
                self.store.register_currency(currency)

    def register(self, currency: Currency) -> Currency:
        return self.store.register_currency(currency)

    def get(self, code: str) -> Optional[Currency]:
        return self.store.get_currency(code)

    def list_all(self) -> list[Currency]:
        return self.store.list_currencies()

    def format(self, code: str, amount) -> str:
        """Format an amount in the given currency."""
        currency = self.get(code)
        if currency:
            return currency.format(amount)
        return str(amount)
