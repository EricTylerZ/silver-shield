"""
EZ Merit ledger bridge.

This replaces EZ Merit Notify's standalone wallets.json with queries
against the Silver Shield double-entry ledger. EZ Merit becomes the
spending interface; Silver Shield is the ledger of record.

Merit costs per commander's policy (CI 40-703.7):
  - 22 merit per email recipient
  - 22 merit per SMTP relay
  - 2 merit per announcement
  - 10 merit per confirmation

Per CI 40-703.2: only the head of household mints merit.
"""

from decimal import Decimal
from typing import Optional

from ..resources.tracker import ResourceTracker

# Cost table per commander's policy CI 40-703.7
MERIT_COSTS = {
    "email_send": Decimal("22"),
    "smtp_relay": Decimal("22"),
    "announcement": Decimal("2"),
    "confirmation": Decimal("10"),
}


class MeritBridge:
    """Bridge between EZ Merit Notify and Silver Shield's ledger."""

    def __init__(self, tracker: ResourceTracker):
        self.tracker = tracker

    def get_balance(self, project_slug: str) -> Decimal:
        """
        Get merit balance for a project.

        This is what EZ Merit Notify should call instead of reading wallets.json.
        """
        return self.tracker.get_balance(project_slug, "MERIT")

    def can_afford(self, project_slug: str, action: str,
                   count: int = 1) -> dict:
        """Check if a project can afford a merit action."""
        cost_per = MERIT_COSTS.get(action)
        if cost_per is None:
            raise ValueError(f"Unknown merit action: {action}")

        total_cost = cost_per * count
        balance = self.get_balance(project_slug)
        affordable = balance >= total_cost

        return {
            "affordable": affordable,
            "balance": str(balance),
            "cost_per_unit": str(cost_per),
            "total_cost": str(total_cost),
            "count": count,
            "action": action,
            "shortfall": str(total_cost - balance) if not affordable else "0",
        }

    def spend(
        self,
        project_slug: str,
        action: str,
        count: int = 1,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Spend merit for a project action.

        Validates affordability first, then records the transaction
        in the double-entry ledger.
        """
        cost_per = MERIT_COSTS.get(action)
        if cost_per is None:
            raise ValueError(f"Unknown merit action: {action}")

        total_cost = cost_per * count
        check = self.can_afford(project_slug, action, count)

        if not check["affordable"]:
            raise ValueError(
                f"Insufficient merit: need {total_cost}, have {check['balance']}. "
                f"Shortfall: {check['shortfall']}"
            )

        desc = description or f"Merit spend: {action} x{count}"

        return self.tracker.record_spending(
            entity_slug=project_slug,
            amount=total_cost,
            currency_code="MERIT",
            description=desc,
            category=f"merit_{action}",
            source_system="ez_merit",
            idempotency_key=idempotency_key,
        )

    def mint_to_treasury(
        self,
        treasury_slug: str,
        amount: Decimal,
        authorized_by: str,
        description: str = "Merit minted by head of household",
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Mint merit into a treasury entity.

        Per CI 40-703.2: only the head of household mints.
        """
        return self.tracker.mint(
            entity_slug=treasury_slug,
            amount=amount,
            currency_code="MERIT",
            description=description,
            authorized_by=authorized_by,
            idempotency_key=idempotency_key,
        )

    def allocate_to_project(
        self,
        treasury_slug: str,
        project_slug: str,
        amount: Decimal,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Allocate merit from treasury to a project.

        This is the proper way to fund project merit balances.
        """
        desc = description or f"Merit allocation to {project_slug}"
        return self.tracker.allocate(
            from_entity_slug=treasury_slug,
            to_entity_slug=project_slug,
            amount=amount,
            currency_code="MERIT",
            description=desc,
            idempotency_key=idempotency_key,
        )

    def get_cost_table(self) -> dict:
        """Return the current merit cost table."""
        return {k: str(v) for k, v in MERIT_COSTS.items()}
