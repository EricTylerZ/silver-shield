"""
Account operations.

Open, close, query balance, list entries for an account.
Each account belongs to one entity and holds one currency.
"""

from decimal import Decimal
from typing import Optional

from .models import Account, AccountType, EntryType
from ..storage.base import StorageBackend


class AccountManager:
    """Manages accounts within entities."""

    def __init__(self, store: StorageBackend):
        self.store = store

    def open(self, entity_id: str, currency_code: str,
             account_type: AccountType, name: str,
             metadata: Optional[dict] = None) -> Account:
        """Open a new account for an entity."""
        account = Account(
            entity_id=entity_id,
            currency_code=currency_code,
            account_type=account_type,
            name=name,
            metadata=metadata or {},
        )
        self.store.create_account(account)
        return account

    def close(self, account_id: str) -> Account:
        """Mark an account as inactive. Does not delete entries."""
        account = self.store.get_account(account_id)
        if account is None:
            raise ValueError(f"Account '{account_id}' not found")
        balance = self.balance(account_id)
        if balance != Decimal("0"):
            raise ValueError(
                f"Cannot close account with non-zero balance: {balance}"
            )
        account.is_active = False
        self.store.update_account(account)
        return account

    def get(self, account_id: str) -> Optional[Account]:
        return self.store.get_account(account_id)

    def list_for_entity(self, entity_id: str) -> list[Account]:
        return self.store.list_accounts(entity_id)

    def balance(self, account_id: str) -> Decimal:
        """
        Current balance from the most recent entry's balance_after.
        Returns 0 if no entries exist.
        """
        latest = self.store.get_latest_entry(account_id)
        if latest is None:
            return Decimal("0")
        return latest.balance_after

    def trial_balance(self, entity_id: str) -> list[dict]:
        """
        Trial balance for all accounts of an entity.
        Returns list of {account, balance, currency_code}.
        """
        accounts = self.store.list_accounts(entity_id)
        result = []
        for acct in accounts:
            bal = self.balance(acct.id)
            result.append({
                "account": acct,
                "balance": bal,
                "currency_code": acct.currency_code,
            })
        return result
