"""
Double-entry transaction helpers.

Higher-level operations built on the ledger engine. These handle common
transaction patterns (bank imports, transfers, expense recording) and
ensure the correct account pairings.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from .models import Entry, Account, AccountType
from .ledger import Ledger
from .accounts import AccountManager


class DoubleEntry:
    """High-level double-entry transaction patterns."""

    def __init__(self, ledger: Ledger, accounts: AccountManager):
        self.ledger = ledger
        self.accounts = accounts

    def record_deposit(
        self,
        account_id: str,
        amount: Decimal,
        description: str,
        category: str = "",
        entry_date: Optional[date] = None,
        reference_id: Optional[str] = None,
        source_system: str = "bank_import",
        idempotency_key: Optional[str] = None,
    ) -> tuple[Entry, Entry]:
        """
        Record a bank deposit.

        Debit: the bank account (asset increases)
        Credit: an income account (determined by category) or suspense
        """
        account = self.accounts.get(account_id)
        if account is None:
            raise ValueError(f"Account '{account_id}' not found")

        # Find or use suspense as the counter-account
        income_accounts = self.accounts.list_for_entity(account.entity_id)
        income_acct = self._find_counter_account(
            income_accounts, AccountType.INCOME, category
        )
        if income_acct is None:
            income_acct = self._find_counter_account(
                income_accounts, AccountType.EQUITY, "suspense"
            )

        if income_acct is None:
            raise ValueError(
                f"No income or suspense account found for entity "
                f"of account '{account_id}'"
            )

        return self.ledger.record_transaction(
            debit_account_id=account_id,
            credit_account_id=income_acct.id,
            amount=amount,
            description=description,
            entry_date=entry_date,
            reference_id=reference_id,
            source_system=source_system,
            idempotency_key=idempotency_key,
            metadata={"category": category} if category else {},
        )

    def record_withdrawal(
        self,
        account_id: str,
        amount: Decimal,
        description: str,
        category: str = "",
        entry_date: Optional[date] = None,
        reference_id: Optional[str] = None,
        source_system: str = "bank_import",
        idempotency_key: Optional[str] = None,
    ) -> tuple[Entry, Entry]:
        """
        Record a bank withdrawal.

        Debit: an expense account (determined by category) or suspense
        Credit: the bank account (asset decreases)
        """
        account = self.accounts.get(account_id)
        if account is None:
            raise ValueError(f"Account '{account_id}' not found")

        expense_accounts = self.accounts.list_for_entity(account.entity_id)
        expense_acct = self._find_counter_account(
            expense_accounts, AccountType.EXPENSE, category
        )
        if expense_acct is None:
            expense_acct = self._find_counter_account(
                expense_accounts, AccountType.EQUITY, "suspense"
            )

        if expense_acct is None:
            raise ValueError(
                f"No expense or suspense account found for entity "
                f"of account '{account_id}'"
            )

        return self.ledger.record_transaction(
            debit_account_id=expense_acct.id,
            credit_account_id=account_id,
            amount=amount,
            description=description,
            entry_date=entry_date,
            reference_id=reference_id,
            source_system=source_system,
            idempotency_key=idempotency_key,
            metadata={"category": category} if category else {},
        )

    def transfer(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: Decimal,
        description: str,
        entry_date: Optional[date] = None,
        reference_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> tuple[Entry, Entry]:
        """
        Transfer between two asset accounts.

        Debit: destination (asset increases)
        Credit: source (asset decreases)
        """
        return self.ledger.record_transaction(
            debit_account_id=to_account_id,
            credit_account_id=from_account_id,
            amount=amount,
            description=description,
            entry_date=entry_date,
            reference_id=reference_id,
            source_system="transfer",
            idempotency_key=idempotency_key,
        )

    def record_liability(
        self,
        asset_account_id: str,
        liability_account_id: str,
        amount: Decimal,
        description: str,
        entry_date: Optional[date] = None,
        reference_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> tuple[Entry, Entry]:
        """
        Record receiving money that creates a liability (e.g., parent loan).

        Debit: asset account (cash increases)
        Credit: liability account (debt increases)
        """
        return self.ledger.record_transaction(
            debit_account_id=asset_account_id,
            credit_account_id=liability_account_id,
            amount=amount,
            description=description,
            entry_date=entry_date,
            reference_id=reference_id,
            source_system="bank_import",
            idempotency_key=idempotency_key,
            metadata={"category": "parent_debt"},
        )

    def _find_counter_account(
        self, accounts: list[Account], account_type: AccountType,
        category_hint: str
    ) -> Optional[Account]:
        """Find a matching counter-account by type and optional category."""
        category_lower = category_hint.lower() if category_hint else ""

        # Try to match by category in metadata or name
        for acct in accounts:
            if acct.account_type != account_type or not acct.is_active:
                continue
            acct_cat = acct.metadata.get("category", "").lower()
            acct_name = acct.name.lower()
            if category_lower and (category_lower in acct_cat
                                   or category_lower in acct_name):
                return acct

        # Fall back to any active account of that type
        for acct in accounts:
            if acct.account_type == account_type and acct.is_active:
                return acct

        return None
