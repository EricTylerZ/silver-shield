"""
Abstract storage interface for Silver Shield.

Two backends share this interface:
  - json_store.py: JSONL files (local, no deps)
  - supabase_store.py: Supabase (production, Angular frontend)

The core engine calls only these methods. It never knows
which backend is in use.
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..core.models import Entity, Account, Currency, Entry, ExchangeRate


class StorageBackend(ABC):
    """Abstract storage interface."""

    # --- Entity ---

    @abstractmethod
    def create_entity(self, entity: Entity) -> Entity:
        ...

    @abstractmethod
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        ...

    @abstractmethod
    def get_entity_by_slug(self, slug: str) -> Optional[Entity]:
        ...

    @abstractmethod
    def list_entities(self, parent_id: Optional[str] = None) -> list[Entity]:
        ...

    @abstractmethod
    def update_entity(self, entity: Entity) -> Entity:
        ...

    # --- Account ---

    @abstractmethod
    def create_account(self, account: Account) -> Account:
        ...

    @abstractmethod
    def get_account(self, account_id: str) -> Optional[Account]:
        ...

    @abstractmethod
    def list_accounts(self, entity_id: str) -> list[Account]:
        ...

    @abstractmethod
    def update_account(self, account: Account) -> Account:
        ...

    # --- Entry (append-only) ---

    @abstractmethod
    def append_entry(self, entry: Entry) -> Entry:
        ...

    @abstractmethod
    def get_entry(self, entry_id: str) -> Optional[Entry]:
        ...

    @abstractmethod
    def get_entries(self, account_id: str, limit: int = 100,
                    offset: int = 0) -> list[Entry]:
        ...

    @abstractmethod
    def get_latest_entry(self, account_id: str) -> Optional[Entry]:
        ...

    @abstractmethod
    def find_by_idempotency_key(self, key: str) -> Optional[Entry]:
        ...

    @abstractmethod
    def get_entries_by_transaction(self, transaction_id: str) -> list[Entry]:
        ...

    # --- Currency ---

    @abstractmethod
    def register_currency(self, currency: Currency) -> Currency:
        ...

    @abstractmethod
    def get_currency(self, code: str) -> Optional[Currency]:
        ...

    @abstractmethod
    def list_currencies(self) -> list[Currency]:
        ...

    # --- Exchange Rate ---

    @abstractmethod
    def record_rate(self, rate: ExchangeRate) -> ExchangeRate:
        ...

    @abstractmethod
    def get_latest_rate(self, from_currency: str,
                        to_currency: str) -> Optional[ExchangeRate]:
        ...
