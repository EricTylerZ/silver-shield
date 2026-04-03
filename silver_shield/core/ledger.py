"""
Append-only ledger engine.

The heart of Silver Shield. Enforces three invariants:
  1. Append-only -- no entry is ever modified or deleted
  2. Double-entry -- every record_transaction creates exactly two entries
     whose amounts are equal (debit == credit)
  3. Idempotency -- if an idempotency_key exists, return existing entries

Balance is computed from the denormalized balance_after field on the most
recent entry for each account.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from .models import Entry, EntryType, Account, AccountType, Transaction, Authorization
from ..storage.base import StorageBackend


class Ledger:
    """Append-only double-entry ledger."""

    def __init__(self, store: StorageBackend):
        self.store = store

    def record_transaction(
        self,
        debit_account_id: str,
        credit_account_id: str,
        amount: Decimal,
        description: str,
        entry_date: Optional[date] = None,
        reference_id: Optional[str] = None,
        source_system: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[dict] = None,
        authorization: Optional[Authorization] = None,
    ) -> tuple[Entry, Entry]:
        """
        Record a double-entry transaction.

        Creates one debit entry and one credit entry linked by transaction_id.
        The debit account's balance is adjusted based on its normal balance
        direction, and likewise for the credit account.

        Authorization is attached to both entries when provided. Per policy,
        every entry should carry authorization: who said so, in what words,
        and where that's on record.

        Returns (debit_entry, credit_entry).
        """
        if amount <= 0:
            raise ValueError("Transaction amount must be positive")

        # Idempotency check
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing:
                entries = self.store.get_entries_by_transaction(
                    existing.transaction_id
                )
                if len(entries) == 2:
                    debit = next(e for e in entries if e.entry_type == EntryType.DEBIT)
                    credit = next(e for e in entries if e.entry_type == EntryType.CREDIT)
                    return debit, credit

        # Validate accounts exist
        debit_acct = self.store.get_account(debit_account_id)
        credit_acct = self.store.get_account(credit_account_id)
        if debit_acct is None:
            raise ValueError(f"Debit account '{debit_account_id}' not found")
        if credit_acct is None:
            raise ValueError(f"Credit account '{credit_account_id}' not found")

        txn = Transaction(
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=amount,
            description=description,
            entry_date=entry_date or date.today(),
            reference_id=reference_id,
            source_system=source_system,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
        )

        # Compute new balances
        debit_balance = self._compute_new_balance(
            debit_acct, EntryType.DEBIT, amount
        )
        credit_balance = self._compute_new_balance(
            credit_acct, EntryType.CREDIT, amount
        )

        # Create entries
        debit_entry = Entry(
            account_id=debit_account_id,
            transaction_id=txn.id,
            entry_type=EntryType.DEBIT,
            amount=amount,
            balance_after=debit_balance,
            description=description,
            entry_date=txn.entry_date,
            reference_id=reference_id,
            source_system=source_system,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
        )

        credit_entry = Entry(
            account_id=credit_account_id,
            transaction_id=txn.id,
            entry_type=EntryType.CREDIT,
            amount=amount,
            balance_after=credit_balance,
            description=description,
            entry_date=txn.entry_date,
            reference_id=reference_id,
            source_system=source_system,
            # Only one entry gets the idempotency key
            metadata=metadata or {},
        )

        self.store.append_entry(debit_entry)
        self.store.append_entry(credit_entry)

        return debit_entry, credit_entry

    def get_balance(self, account_id: str) -> Decimal:
        """Current balance from the most recent entry."""
        latest = self.store.get_latest_entry(account_id)
        return latest.balance_after if latest else Decimal("0")

    def get_entries(self, account_id: str, limit: int = 100,
                    offset: int = 0) -> list[Entry]:
        return self.store.get_entries(account_id, limit, offset)

    def get_transaction(self, transaction_id: str) -> list[Entry]:
        return self.store.get_entries_by_transaction(transaction_id)

    def _compute_new_balance(
        self, account: Account, entry_type: EntryType, amount: Decimal
    ) -> Decimal:
        """
        Compute the new balance after applying an entry.

        Normal balance rules:
          Asset/Expense accounts: debit increases, credit decreases
          Liability/Income/Equity accounts: credit increases, debit decreases
        """
        current = self.get_balance(account.id)

        if account.normal_balance == entry_type:
            return current + amount
        else:
            return current - amount
