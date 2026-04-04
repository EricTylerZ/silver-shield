"""
Resource tracker -- per-entity budgets, balances, spending, and minting.

Wraps the core accounting engine to provide a higher-level API that
sibling projects (auto-agent, EZ Merit, etc.) can call to:
  - Query balances for any entity/currency
  - Record spending (debits expense, credits the asset)
  - Allocate resources between entities (treasury -> project)
  - Mint new currency (human authority required)
  - Get budget summaries

This is the module auto-agent identified as the ecosystem bottleneck.
Every project's treasury balance lives here, not in separate JSON counters.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from ..core.models import AccountType, EntityType, Authorization
from ..core.ledger import Ledger
from ..core.accounts import AccountManager
from ..core.entities import EntityManager
from ..core.currencies import CurrencyRegistry
from ..storage.base import StorageBackend


class ResourceTracker:
    """Per-entity resource tracking on top of the double-entry ledger."""

    def __init__(self, store: StorageBackend):
        self.store = store
        self.ledger = Ledger(store)
        self.accounts = AccountManager(store)
        self.entities = EntityManager(store)
        self.currencies = CurrencyRegistry(store)

    # ------------------------------------------------------------------
    # Balance queries
    # ------------------------------------------------------------------

    def get_balance(self, entity_slug: str, currency_code: str,
                    account_type: AccountType = AccountType.ASSET) -> Decimal:
        """Get the current balance for an entity's account in a given currency."""
        entity = self.entities.get_by_slug(entity_slug)
        if entity is None:
            raise ValueError(f"Entity '{entity_slug}' not found")

        acct = self._find_account(entity.id, currency_code, account_type)
        if acct is None:
            return Decimal("0")

        return self.ledger.get_balance(acct.id)

    def get_all_balances(self, entity_slug: str) -> list[dict]:
        """Get balances across all accounts for an entity."""
        entity = self.entities.get_by_slug(entity_slug)
        if entity is None:
            raise ValueError(f"Entity '{entity_slug}' not found")

        return self.accounts.trial_balance(entity.id)

    def get_entity_summary(self, entity_slug: str) -> dict:
        """Full resource summary: balances by currency, account breakdown."""
        entity = self.entities.get_by_slug(entity_slug)
        if entity is None:
            raise ValueError(f"Entity '{entity_slug}' not found")

        trial = self.accounts.trial_balance(entity.id)
        by_currency: dict[str, dict] = {}

        for row in trial:
            acct = row["account"]
            bal = row["balance"]
            cc = acct.currency_code

            if cc not in by_currency:
                by_currency[cc] = {"assets": Decimal("0"), "liabilities": Decimal("0"),
                                   "income": Decimal("0"), "expenses": Decimal("0"),
                                   "equity": Decimal("0")}

            bucket = {
                AccountType.ASSET: "assets", AccountType.LIABILITY: "liabilities",
                AccountType.INCOME: "income", AccountType.EXPENSE: "expenses",
                AccountType.EQUITY: "equity",
            }[acct.account_type]
            by_currency[cc][bucket] += bal

        return {
            "entity": entity.slug,
            "name": entity.name,
            "type": entity.entity_type.value,
            "balances": {
                cc: {k: str(v) for k, v in buckets.items()}
                for cc, buckets in by_currency.items()
            },
            "account_count": len(trial),
        }

    # ------------------------------------------------------------------
    # Spending
    # ------------------------------------------------------------------

    def record_spending(
        self,
        entity_slug: str,
        amount: Decimal,
        currency_code: str,
        description: str,
        category: str = "operating",
        source_system: str = "manual",
        authorization: Optional[Authorization] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Record spending for an entity.

        Debit: expense account (increases expense)
        Credit: asset account (decreases available funds)
        """
        entity = self.entities.get_by_slug(entity_slug)
        if entity is None:
            raise ValueError(f"Entity '{entity_slug}' not found")

        asset_acct = self._find_account(entity.id, currency_code, AccountType.ASSET)
        if asset_acct is None:
            raise ValueError(f"No {currency_code} asset account for '{entity_slug}'")

        expense_acct = self._find_or_create_account(
            entity.id, currency_code, AccountType.EXPENSE,
            f"{category} expenses", {"category": category},
        )

        debit, credit = self.ledger.record_transaction(
            debit_account_id=expense_acct.id,
            credit_account_id=asset_acct.id,
            amount=amount,
            description=description,
            source_system=source_system,
            idempotency_key=idempotency_key,
            metadata={"category": category},
            authorization=authorization,
        )

        return {
            "transaction_id": debit.transaction_id,
            "entity": entity_slug,
            "amount": str(amount),
            "currency": currency_code,
            "balance_after": str(credit.balance_after),
            "description": description,
        }

    # ------------------------------------------------------------------
    # Allocation (treasury -> project)
    # ------------------------------------------------------------------

    def allocate(
        self,
        from_entity_slug: str,
        to_entity_slug: str,
        amount: Decimal,
        currency_code: str,
        description: str,
        authorization: Optional[Authorization] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Allocate resources from one entity to another.

        This is the proper way to fund project accounts: the parent entity
        (treasury) transfers to the child entity's asset account.
        """
        from_entity = self.entities.get_by_slug(from_entity_slug)
        to_entity = self.entities.get_by_slug(to_entity_slug)
        if from_entity is None:
            raise ValueError(f"Source entity '{from_entity_slug}' not found")
        if to_entity is None:
            raise ValueError(f"Destination entity '{to_entity_slug}' not found")

        from_acct = self._find_account(from_entity.id, currency_code, AccountType.ASSET)
        if from_acct is None:
            raise ValueError(f"No {currency_code} asset account for '{from_entity_slug}'")

        to_acct = self._find_or_create_account(
            to_entity.id, currency_code, AccountType.ASSET,
            f"{currency_code} treasury",
        )

        debit, credit = self.ledger.record_transaction(
            debit_account_id=to_acct.id,
            credit_account_id=from_acct.id,
            amount=amount,
            description=description,
            source_system="household_allocation",
            idempotency_key=idempotency_key,
            metadata={"from_entity": from_entity_slug, "to_entity": to_entity_slug},
            authorization=authorization,
        )

        return {
            "transaction_id": debit.transaction_id,
            "from": from_entity_slug,
            "to": to_entity_slug,
            "amount": str(amount),
            "currency": currency_code,
            "from_balance_after": str(credit.balance_after),
            "to_balance_after": str(debit.balance_after),
        }

    # ------------------------------------------------------------------
    # Minting (human authority required)
    # ------------------------------------------------------------------

    def mint(
        self,
        entity_slug: str,
        amount: Decimal,
        currency_code: str,
        description: str,
        authorized_by: Optional[str] = None,
        authorization: Optional[Authorization] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Mint new currency into an entity's treasury.

        Only the human authority (or someone they delegate to) can mint.
        Creates equity (the source) and asset (the destination).

        Per CI 40-703.2: only the head of household mints.
        """
        entity = self.entities.get_by_slug(entity_slug)
        if entity is None:
            raise ValueError(f"Entity '{entity_slug}' not found")

        # Verify human authority
        if not self.entities.validate_human_authority(entity.id):
            raise PermissionError(
                f"Entity '{entity_slug}' has no valid human authority chain"
            )

        # If authorized_by is provided, verify it's the human authority
        if authorized_by:
            authority = self.entities.get_by_slug(authorized_by)
            if authority is None or not authority.is_human():
                raise PermissionError(
                    f"Authorizer '{authorized_by}' is not a valid human authority"
                )

        # Build Authorization if not provided explicitly
        if authorization is None and authorized_by:
            authorization = Authorization(
                authorized_by=authorized_by,
                statement=description,
                reference=idempotency_key or "manual",
            )

        asset_acct = self._find_or_create_account(
            entity.id, currency_code, AccountType.ASSET,
            f"{currency_code} treasury",
        )
        equity_acct = self._find_or_create_account(
            entity.id, currency_code, AccountType.EQUITY,
            f"{currency_code} minted",
            {"category": "mint"},
        )

        debit, credit = self.ledger.record_transaction(
            debit_account_id=asset_acct.id,
            credit_account_id=equity_acct.id,
            amount=amount,
            description=description,
            source_system="mint",
            idempotency_key=idempotency_key,
            metadata={"authorized_by": authorized_by or "head_of_household"},
            authorization=authorization,
        )

        return {
            "transaction_id": debit.transaction_id,
            "entity": entity_slug,
            "amount": str(amount),
            "currency": currency_code,
            "balance_after": str(debit.balance_after),
            "description": description,
        }

    # ------------------------------------------------------------------
    # Corrections (append-only reversal)
    # ------------------------------------------------------------------

    def correct_allocation(
        self,
        original_transaction_id: str,
        reason: str,
        authorization: Authorization,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Reverse an unauthorized or erroneous allocation.

        Appends corrective entries that cancel the original transaction.
        The authorization (who said so, verbatim statement, reference)
        is attached to both corrective entries. The original entries
        remain in the ledger untouched -- append-only.
        """
        debit, credit = self.ledger.record_correction(
            original_transaction_id=original_transaction_id,
            reason=reason,
            authorization=authorization,
            idempotency_key=idempotency_key,
        )

        return {
            "correction_transaction_id": debit.transaction_id,
            "original_transaction_id": original_transaction_id,
            "amount": str(debit.amount),
            "reason": reason,
            "authorized_by": authorization.authorized_by,
            "authorization_statement": authorization.statement,
            "authorization_reference": authorization.reference,
            "debit_balance_after": str(debit.balance_after),
            "credit_balance_after": str(credit.balance_after),
        }

    def find_unauthorized_allocations(self, entity_slug: str,
                                      currency_code: Optional[str] = None,
                                      ) -> list[dict]:
        """
        Find allocation entries that lack authorization.

        Returns entries from 'household_allocation' source_system
        where authorization is None.
        """
        entity = self.entities.get_by_slug(entity_slug)
        if entity is None:
            raise ValueError(f"Entity '{entity_slug}' not found")

        accounts = self.accounts.list_for_entity(entity.id)
        if currency_code:
            accounts = [a for a in accounts if a.currency_code == currency_code]

        unauthorized = []
        seen_txns = set()
        for acct in accounts:
            entries = self.ledger.get_entries(acct.id, limit=1000)
            for e in entries:
                if (e.source_system == "household_allocation"
                        and e.authorization is None
                        and e.transaction_id not in seen_txns):
                    seen_txns.add(e.transaction_id)
                    unauthorized.append({
                        "transaction_id": e.transaction_id,
                        "account_id": e.account_id,
                        "amount": str(e.amount),
                        "description": e.description,
                        "entry_date": e.entry_date.isoformat(),
                    })

        return unauthorized

    # ------------------------------------------------------------------
    # Ledger access
    # ------------------------------------------------------------------

    def get_entries(self, entity_slug: str, currency_code: Optional[str] = None,
                    limit: int = 50) -> list[dict]:
        """Get recent ledger entries for an entity, optionally filtered by currency."""
        entity = self.entities.get_by_slug(entity_slug)
        if entity is None:
            raise ValueError(f"Entity '{entity_slug}' not found")

        accounts = self.accounts.list_for_entity(entity.id)
        if currency_code:
            accounts = [a for a in accounts if a.currency_code == currency_code]

        all_entries = []
        for acct in accounts:
            entries = self.ledger.get_entries(acct.id, limit=limit)
            for e in entries:
                all_entries.append({
                    "id": e.id,
                    "account_id": e.account_id,
                    "account_name": acct.name,
                    "transaction_id": e.transaction_id,
                    "entry_type": e.entry_type.value,
                    "amount": str(e.amount),
                    "balance_after": str(e.balance_after),
                    "description": e.description,
                    "entry_date": e.entry_date.isoformat(),
                    "source_system": e.source_system,
                    "currency": acct.currency_code,
                })

        all_entries.sort(key=lambda e: e["entry_date"], reverse=True)
        return all_entries[:limit]

    # ------------------------------------------------------------------
    # Hierarchy queries
    # ------------------------------------------------------------------

    def get_entity_tree(self) -> list[dict]:
        """Full entity hierarchy with account counts and balances."""
        all_entities = self.entities.list_all()
        tree = []
        for entity in all_entities:
            accounts = self.accounts.list_for_entity(entity.id)
            acct_list = []
            for acct in accounts:
                bal = self.ledger.get_balance(acct.id)
                acct_list.append({
                    "id": acct.id,
                    "name": acct.name,
                    "type": acct.account_type.value,
                    "currency": acct.currency_code,
                    "balance": str(bal),
                    "active": acct.is_active,
                })

            tree.append({
                "id": entity.id,
                "slug": entity.slug,
                "name": entity.name,
                "type": entity.entity_type.value,
                "parent_id": entity.parent_id,
                "human_authority": entity.human_authority,
                "accounts": acct_list,
            })

        return tree

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_account(self, entity_id: str, currency_code: str,
                      account_type: AccountType):
        """Find an existing account by entity, currency, and type."""
        accounts = self.accounts.list_for_entity(entity_id)
        for acct in accounts:
            if (acct.currency_code == currency_code
                    and acct.account_type == account_type
                    and acct.is_active):
                return acct
        return None

    def _find_or_create_account(self, entity_id: str, currency_code: str,
                                account_type: AccountType, name: str,
                                metadata: Optional[dict] = None):
        """Find or create an account."""
        existing = self._find_account(entity_id, currency_code, account_type)
        if existing:
            return existing
        return self.accounts.open(
            entity_id, currency_code, account_type, name,
            metadata=metadata,
        )
