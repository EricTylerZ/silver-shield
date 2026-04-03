"""
JSONL file-based storage backend.

Follows the EZ Merit store.py pattern:
  - entities.json, accounts.json, currencies.json: full JSON arrays
  - ledger.jsonl: append-only, one JSON object per line
  - rates.jsonl: append-only exchange rate history

All files live under a configurable data_dir (never committed to repo).
"""

import json
import threading
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .base import StorageBackend
from ..core.models import (
    Entity, Account, Currency, Entry, ExchangeRate,
    EntityType, AccountType, EntryType, RateSource,
)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, EntityType | AccountType | EntryType | RateSource):
            return o.value
        return super().default(o)


def _entity_to_dict(e: Entity) -> dict:
    return {
        "id": e.id, "slug": e.slug, "name": e.name,
        "entity_type": e.entity_type.value, "parent_id": e.parent_id,
        "human_authority": e.human_authority,
        "created_at": e.created_at.isoformat(),
        "metadata": e.metadata,
    }


def _entity_from_dict(d: dict) -> Entity:
    return Entity(
        id=d["id"], slug=d["slug"], name=d["name"],
        entity_type=EntityType(d["entity_type"]),
        parent_id=d.get("parent_id"),
        human_authority=d.get("human_authority"),
        created_at=datetime.fromisoformat(d["created_at"]),
        metadata=d.get("metadata", {}),
    )


def _account_to_dict(a: Account) -> dict:
    return {
        "id": a.id, "entity_id": a.entity_id,
        "currency_code": a.currency_code,
        "account_type": a.account_type.value, "name": a.name,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat(),
        "metadata": a.metadata,
    }


def _account_from_dict(d: dict) -> Account:
    return Account(
        id=d["id"], entity_id=d["entity_id"],
        currency_code=d["currency_code"],
        account_type=AccountType(d["account_type"]),
        name=d["name"], is_active=d.get("is_active", True),
        created_at=datetime.fromisoformat(d["created_at"]),
        metadata=d.get("metadata", {}),
    )


def _entry_to_dict(e: Entry) -> dict:
    return {
        "id": e.id, "account_id": e.account_id,
        "transaction_id": e.transaction_id,
        "entry_type": e.entry_type.value,
        "amount": str(e.amount),
        "balance_after": str(e.balance_after),
        "description": e.description,
        "entry_date": e.entry_date.isoformat(),
        "created_at": e.created_at.isoformat(),
        "reference_id": e.reference_id,
        "source_system": e.source_system,
        "idempotency_key": e.idempotency_key,
        "metadata": e.metadata,
    }


def _entry_from_dict(d: dict) -> Entry:
    return Entry(
        id=d["id"], account_id=d["account_id"],
        transaction_id=d["transaction_id"],
        entry_type=EntryType(d["entry_type"]),
        amount=Decimal(d["amount"]),
        balance_after=Decimal(d["balance_after"]),
        description=d["description"],
        entry_date=date.fromisoformat(d["entry_date"]),
        created_at=datetime.fromisoformat(d["created_at"]),
        reference_id=d.get("reference_id"),
        source_system=d.get("source_system"),
        idempotency_key=d.get("idempotency_key"),
        metadata=d.get("metadata", {}),
    )


def _currency_to_dict(c: Currency) -> dict:
    return {
        "code": c.code, "name": c.name, "symbol": c.symbol,
        "precision": c.precision, "is_convertible": c.is_convertible,
        "rate_source": c.rate_source.value,
    }


def _currency_from_dict(d: dict) -> Currency:
    return Currency(
        code=d["code"], name=d["name"], symbol=d["symbol"],
        precision=d["precision"],
        is_convertible=d.get("is_convertible", True),
        rate_source=RateSource(d.get("rate_source", "fixed")),
    )


def _rate_to_dict(r: ExchangeRate) -> dict:
    return {
        "id": r.id, "from_currency": r.from_currency,
        "to_currency": r.to_currency, "rate": str(r.rate),
        "source": r.source,
        "recorded_at": r.recorded_at.isoformat(),
    }


def _rate_from_dict(d: dict) -> ExchangeRate:
    return ExchangeRate(
        id=d["id"], from_currency=d["from_currency"],
        to_currency=d["to_currency"], rate=Decimal(d["rate"]),
        source=d["source"],
        recorded_at=datetime.fromisoformat(d["recorded_at"]),
    )


class JsonStore(StorageBackend):
    """File-based storage using JSON and JSONL."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

        self._entities_path = self.data_dir / "entities.json"
        self._accounts_path = self.data_dir / "accounts.json"
        self._currencies_path = self.data_dir / "currencies.json"
        self._ledger_path = self.data_dir / "ledger.jsonl"
        self._rates_path = self.data_dir / "rates.jsonl"

    # --- Helpers ---

    def _read_json(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with open(path) as f:
            return json.load(f)

    def _write_json(self, path: Path, data: list[dict]):
        with open(path, "w") as f:
            json.dump(data, f, indent=2, cls=DecimalEncoder)

    def _append_jsonl(self, path: Path, record: dict):
        with open(path, "a") as f:
            f.write(json.dumps(record, cls=DecimalEncoder) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        records = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    # --- Entity ---

    def create_entity(self, entity: Entity) -> Entity:
        with self._lock:
            data = self._read_json(self._entities_path)
            data.append(_entity_to_dict(entity))
            self._write_json(self._entities_path, data)
        return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        for d in self._read_json(self._entities_path):
            if d["id"] == entity_id:
                return _entity_from_dict(d)
        return None

    def get_entity_by_slug(self, slug: str) -> Optional[Entity]:
        for d in self._read_json(self._entities_path):
            if d["slug"] == slug:
                return _entity_from_dict(d)
        return None

    def list_entities(self, parent_id: Optional[str] = None) -> list[Entity]:
        data = self._read_json(self._entities_path)
        if parent_id is not None:
            data = [d for d in data if d.get("parent_id") == parent_id]
        return [_entity_from_dict(d) for d in data]

    def update_entity(self, entity: Entity) -> Entity:
        with self._lock:
            data = self._read_json(self._entities_path)
            data = [d if d["id"] != entity.id else _entity_to_dict(entity)
                    for d in data]
            self._write_json(self._entities_path, data)
        return entity

    # --- Account ---

    def create_account(self, account: Account) -> Account:
        with self._lock:
            data = self._read_json(self._accounts_path)
            data.append(_account_to_dict(account))
            self._write_json(self._accounts_path, data)
        return account

    def get_account(self, account_id: str) -> Optional[Account]:
        for d in self._read_json(self._accounts_path):
            if d["id"] == account_id:
                return _account_from_dict(d)
        return None

    def list_accounts(self, entity_id: str) -> list[Account]:
        return [_account_from_dict(d)
                for d in self._read_json(self._accounts_path)
                if d["entity_id"] == entity_id]

    def update_account(self, account: Account) -> Account:
        with self._lock:
            data = self._read_json(self._accounts_path)
            data = [d if d["id"] != account.id else _account_to_dict(account)
                    for d in data]
            self._write_json(self._accounts_path, data)
        return account

    # --- Entry (append-only) ---

    def append_entry(self, entry: Entry) -> Entry:
        with self._lock:
            self._append_jsonl(self._ledger_path, _entry_to_dict(entry))
        return entry

    def get_entry(self, entry_id: str) -> Optional[Entry]:
        for d in self._read_jsonl(self._ledger_path):
            if d["id"] == entry_id:
                return _entry_from_dict(d)
        return None

    def get_entries(self, account_id: str, limit: int = 100,
                    offset: int = 0) -> list[Entry]:
        entries = [_entry_from_dict(d)
                   for d in self._read_jsonl(self._ledger_path)
                   if d["account_id"] == account_id]
        # Most recent first
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[offset:offset + limit]

    def get_latest_entry(self, account_id: str) -> Optional[Entry]:
        entries = self.get_entries(account_id, limit=1)
        return entries[0] if entries else None

    def find_by_idempotency_key(self, key: str) -> Optional[Entry]:
        for d in self._read_jsonl(self._ledger_path):
            if d.get("idempotency_key") == key:
                return _entry_from_dict(d)
        return None

    def get_entries_by_transaction(self, transaction_id: str) -> list[Entry]:
        return [_entry_from_dict(d)
                for d in self._read_jsonl(self._ledger_path)
                if d["transaction_id"] == transaction_id]

    # --- Currency ---

    def register_currency(self, currency: Currency) -> Currency:
        with self._lock:
            data = self._read_json(self._currencies_path)
            # Upsert
            data = [d for d in data if d["code"] != currency.code]
            data.append(_currency_to_dict(currency))
            self._write_json(self._currencies_path, data)
        return currency

    def get_currency(self, code: str) -> Optional[Currency]:
        for d in self._read_json(self._currencies_path):
            if d["code"] == code:
                return _currency_from_dict(d)
        return None

    def list_currencies(self) -> list[Currency]:
        return [_currency_from_dict(d)
                for d in self._read_json(self._currencies_path)]

    # --- Exchange Rate ---

    def record_rate(self, rate: ExchangeRate) -> ExchangeRate:
        with self._lock:
            self._append_jsonl(self._rates_path, _rate_to_dict(rate))
        return rate

    def get_latest_rate(self, from_currency: str,
                        to_currency: str) -> Optional[ExchangeRate]:
        best = None
        for d in self._read_jsonl(self._rates_path):
            if (d["from_currency"] == from_currency
                    and d["to_currency"] == to_currency):
                rate = _rate_from_dict(d)
                if best is None or rate.recorded_at > best.recorded_at:
                    best = rate
        return best
