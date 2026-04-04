"""
Non-monetary asset tracker -- financial dimension of physical resources.

Tracks the VALUE and COST side of household assets: vehicles, property,
insurance policies, and their ongoing costs (depreciation, maintenance,
insurance premiums). Each asset is an entity with accounts in the core
ledger, so all the same double-entry invariants apply.

Assets are registered as sub-entities under their owner. Financial events
(purchase, depreciation, maintenance, insurance payment) are recorded as
ledger transactions against the asset's accounts.

This module answers: "What is this asset worth, what has it cost, and
what are the recurring obligations?"
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from ..core.models import (
    AccountType, EntityType, Authorization,
)
from ..core.ledger import Ledger
from ..core.accounts import AccountManager
from ..core.entities import EntityManager
from ..storage.base import StorageBackend


class AssetCategory(str, Enum):
    VEHICLE = "vehicle"
    PROPERTY = "property"
    INSURANCE_POLICY = "insurance_policy"
    EQUIPMENT = "equipment"
    OTHER = "other"


class AssetTracker:
    """Track the financial dimension of non-monetary household assets."""

    def __init__(self, store: StorageBackend):
        self.store = store
        self.ledger = Ledger(store)
        self.accounts = AccountManager(store)
        self.entities = EntityManager(store)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_asset(
        self,
        owner_slug: str,
        name: str,
        slug: str,
        category: AssetCategory,
        acquired_date: Optional[date] = None,
        original_value: Decimal = Decimal("0"),
        currency_code: str = "USD",
        authorization: Optional[Authorization] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Register a physical asset under an owner entity.

        Creates the asset as a project-type sub-entity with:
          - An asset account (current book value)
          - An expense account (accumulated costs: maintenance, insurance)
          - An equity account (original capitalization)

        If original_value > 0, records the initial capitalization.
        """
        owner = self.entities.get_by_slug(owner_slug)
        if owner is None:
            raise ValueError(f"Owner entity '{owner_slug}' not found")

        asset_meta = {
            "asset_category": category.value,
            "acquired_date": (acquired_date or date.today()).isoformat(),
            **(metadata or {}),
        }

        entity = self.entities.create(
            name=name,
            slug=slug,
            entity_type=EntityType.PROJECT,
            parent_id=owner.id,
            metadata=asset_meta,
        )

        # Create standard accounts for this asset
        value_acct = self.accounts.open(
            entity.id, currency_code, AccountType.ASSET,
            f"{name} book value",
        )
        cost_acct = self.accounts.open(
            entity.id, currency_code, AccountType.EXPENSE,
            f"{name} costs",
            metadata={"category": "maintenance"},
        )
        equity_acct = self.accounts.open(
            entity.id, currency_code, AccountType.EQUITY,
            f"{name} capitalization",
        )

        result = {
            "entity_id": entity.id,
            "slug": slug,
            "name": name,
            "category": category.value,
            "owner": owner_slug,
            "currency": currency_code,
            "value_account_id": value_acct.id,
            "cost_account_id": cost_acct.id,
            "equity_account_id": equity_acct.id,
        }

        # Record initial capitalization if value provided
        if original_value > 0:
            debit, credit = self.ledger.record_transaction(
                debit_account_id=value_acct.id,
                credit_account_id=equity_acct.id,
                amount=original_value,
                description=f"Initial capitalization: {name}",
                entry_date=acquired_date or date.today(),
                source_system="asset_registration",
                authorization=authorization,
                metadata={"asset_category": category.value},
            )
            result["book_value"] = str(debit.balance_after)

        return result

    # ------------------------------------------------------------------
    # Depreciation
    # ------------------------------------------------------------------

    def record_depreciation(
        self,
        asset_slug: str,
        amount: Decimal,
        description: str = "",
        entry_date: Optional[date] = None,
        authorization: Optional[Authorization] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Record depreciation on an asset.

        Debit: expense (depreciation cost increases)
        Credit: asset value (book value decreases)
        """
        entity = self.entities.get_by_slug(asset_slug)
        if entity is None:
            raise ValueError(f"Asset '{asset_slug}' not found")

        value_acct = self._find_account(entity.id, AccountType.ASSET)
        cost_acct = self._find_account(entity.id, AccountType.EXPENSE)
        if value_acct is None or cost_acct is None:
            raise ValueError(f"Asset '{asset_slug}' missing required accounts")

        debit, credit = self.ledger.record_transaction(
            debit_account_id=cost_acct.id,
            credit_account_id=value_acct.id,
            amount=amount,
            description=description or f"Depreciation: {asset_slug}",
            entry_date=entry_date,
            source_system="depreciation",
            idempotency_key=idempotency_key,
            metadata={"cost_type": "depreciation"},
            authorization=authorization,
        )

        return {
            "asset": asset_slug,
            "depreciation": str(amount),
            "book_value_after": str(credit.balance_after),
            "total_costs": str(debit.balance_after),
        }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def record_maintenance(
        self,
        asset_slug: str,
        amount: Decimal,
        description: str,
        paid_from_slug: Optional[str] = None,
        entry_date: Optional[date] = None,
        authorization: Optional[Authorization] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Record a maintenance cost against an asset.

        Debit: asset's expense account (cost increases)
        Credit: the paying entity's asset account, or the asset's
                equity account if no payer specified.
        """
        entity = self.entities.get_by_slug(asset_slug)
        if entity is None:
            raise ValueError(f"Asset '{asset_slug}' not found")

        cost_acct = self._find_account(entity.id, AccountType.EXPENSE)
        if cost_acct is None:
            raise ValueError(f"Asset '{asset_slug}' missing expense account")

        # Determine credit account: payer's asset or asset's equity
        if paid_from_slug:
            payer = self.entities.get_by_slug(paid_from_slug)
            if payer is None:
                raise ValueError(f"Payer entity '{paid_from_slug}' not found")
            credit_acct = self._find_account(
                payer.id, AccountType.ASSET, cost_acct.currency_code,
            )
            if credit_acct is None:
                raise ValueError(
                    f"No {cost_acct.currency_code} asset account for '{paid_from_slug}'"
                )
        else:
            credit_acct = self._find_account(entity.id, AccountType.EQUITY)
            if credit_acct is None:
                raise ValueError(f"Asset '{asset_slug}' missing equity account")

        debit, credit = self.ledger.record_transaction(
            debit_account_id=cost_acct.id,
            credit_account_id=credit_acct.id,
            amount=amount,
            description=description,
            entry_date=entry_date,
            source_system="maintenance",
            idempotency_key=idempotency_key,
            metadata={"cost_type": "maintenance"},
            authorization=authorization,
        )

        return {
            "asset": asset_slug,
            "maintenance_cost": str(amount),
            "total_costs": str(debit.balance_after),
            "description": description,
        }

    # ------------------------------------------------------------------
    # Insurance
    # ------------------------------------------------------------------

    def record_insurance_premium(
        self,
        asset_slug: str,
        amount: Decimal,
        description: str,
        policy_id: Optional[str] = None,
        paid_from_slug: Optional[str] = None,
        entry_date: Optional[date] = None,
        authorization: Optional[Authorization] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Record an insurance premium payment for an asset.

        Debit: asset's expense account (cost increases)
        Credit: the paying entity's asset account, or the asset's
                equity account if no payer specified.
        """
        entity = self.entities.get_by_slug(asset_slug)
        if entity is None:
            raise ValueError(f"Asset '{asset_slug}' not found")

        cost_acct = self._find_account(entity.id, AccountType.EXPENSE)
        if cost_acct is None:
            raise ValueError(f"Asset '{asset_slug}' missing expense account")

        if paid_from_slug:
            payer = self.entities.get_by_slug(paid_from_slug)
            if payer is None:
                raise ValueError(f"Payer entity '{paid_from_slug}' not found")
            credit_acct = self._find_account(
                payer.id, AccountType.ASSET, cost_acct.currency_code,
            )
            if credit_acct is None:
                raise ValueError(
                    f"No {cost_acct.currency_code} asset account for '{paid_from_slug}'"
                )
        else:
            credit_acct = self._find_account(entity.id, AccountType.EQUITY)
            if credit_acct is None:
                raise ValueError(f"Asset '{asset_slug}' missing equity account")

        meta = {"cost_type": "insurance"}
        if policy_id:
            meta["policy_id"] = policy_id

        debit, credit = self.ledger.record_transaction(
            debit_account_id=cost_acct.id,
            credit_account_id=credit_acct.id,
            amount=amount,
            description=description,
            entry_date=entry_date,
            source_system="insurance",
            idempotency_key=idempotency_key,
            metadata=meta,
            authorization=authorization,
        )

        return {
            "asset": asset_slug,
            "premium": str(amount),
            "total_costs": str(debit.balance_after),
            "description": description,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_asset_summary(self, asset_slug: str) -> dict:
        """
        Full financial summary of an asset: book value, total costs,
        cost breakdown by type, category, and owner.
        """
        entity = self.entities.get_by_slug(asset_slug)
        if entity is None:
            raise ValueError(f"Asset '{asset_slug}' not found")

        value_acct = self._find_account(entity.id, AccountType.ASSET)
        cost_acct = self._find_account(entity.id, AccountType.EXPENSE)
        equity_acct = self._find_account(entity.id, AccountType.EQUITY)

        book_value = (
            self.ledger.get_balance(value_acct.id)
            if value_acct else Decimal("0")
        )
        total_costs = (
            self.ledger.get_balance(cost_acct.id)
            if cost_acct else Decimal("0")
        )
        capitalization = (
            self.ledger.get_balance(equity_acct.id)
            if equity_acct else Decimal("0")
        )

        # Break down costs by type from entries
        cost_breakdown: dict[str, Decimal] = {}
        if cost_acct:
            entries = self.ledger.get_entries(cost_acct.id, limit=1000)
            for e in entries:
                cost_type = e.metadata.get("cost_type", "other") if e.metadata else "other"
                cost_breakdown[cost_type] = cost_breakdown.get(
                    cost_type, Decimal("0")
                ) + e.amount

        return {
            "slug": asset_slug,
            "name": entity.name,
            "category": entity.metadata.get("asset_category", "other"),
            "acquired_date": entity.metadata.get("acquired_date"),
            "book_value": str(book_value),
            "total_costs": str(total_costs),
            "capitalization": str(capitalization),
            "cost_breakdown": {k: str(v) for k, v in cost_breakdown.items()},
            "owner_id": entity.parent_id,
        }

    def list_assets(self, owner_slug: str) -> list[dict]:
        """List all registered assets for an owner entity."""
        owner = self.entities.get_by_slug(owner_slug)
        if owner is None:
            raise ValueError(f"Owner entity '{owner_slug}' not found")

        children = self.entities.get_children(owner.id)
        assets = []
        for child in children:
            if "asset_category" in child.metadata:
                value_acct = self._find_account(child.id, AccountType.ASSET)
                book_value = (
                    self.ledger.get_balance(value_acct.id)
                    if value_acct else Decimal("0")
                )
                assets.append({
                    "slug": child.slug,
                    "name": child.name,
                    "category": child.metadata["asset_category"],
                    "book_value": str(book_value),
                })

        return assets

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_account(self, entity_id: str, account_type: AccountType,
                      currency_code: Optional[str] = None):
        """Find an active account by entity and type."""
        accounts = self.accounts.list_for_entity(entity_id)
        for acct in accounts:
            if acct.account_type == account_type and acct.is_active:
                if currency_code is None or acct.currency_code == currency_code:
                    return acct
        return None
