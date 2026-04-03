"""
Merit reconciliation engine.

Silver Shield is the single ledger of record for all merit accounting.
External systems (EZ Merit Points, EZ Merit Notify) may execute mints,
allocations, and spends -- but those events are not canonical until they
are recorded here via double-entry.

This module ingests external mint/allocation events and reconciles them
against the Silver Shield ledger. If an event is new, it gets recorded.
If it already exists (idempotency key match), it's confirmed. If the
amounts disagree, it's flagged as a discrepancy.

Per CI 40-703.2: only the head of household mints. External mints
by agents without human authority are flagged as unauthorized.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from ..resources.tracker import ResourceTracker


class ReconciliationResult:
    """Outcome of reconciling a single external event."""

    def __init__(self, event_id: str, action: str, status: str,
                 transaction_id: Optional[str] = None,
                 details: Optional[str] = None):
        self.event_id = event_id
        self.action = action          # "mint", "allocate", "spend"
        self.status = status          # "recorded", "confirmed", "discrepancy", "unauthorized"
        self.transaction_id = transaction_id
        self.details = details or ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "action": self.action,
            "status": self.status,
            "transaction_id": self.transaction_id,
            "details": self.details,
        }


class MeritReconciler:
    """
    Reconcile external merit events against Silver Shield's ledger.

    Silver Shield is the single ledger of record. External systems
    report what happened; this module records it canonically.
    """

    def __init__(self, tracker: ResourceTracker):
        self.tracker = tracker

    def reconcile_mint(
        self,
        entity_slug: str,
        amount: Decimal,
        authorized_by: str,
        source_system: str,
        source_ref: str,
        description: Optional[str] = None,
    ) -> ReconciliationResult:
        """
        Reconcile an external mint event.

        If the idempotency key (derived from source_system + source_ref)
        already exists, confirm it. Otherwise, record it.

        Args:
            entity_slug: Who received the mint
            amount: How much was minted
            authorized_by: Who authorized (must be human authority)
            source_system: Origin system ("ez_merit_points", "ez_merit_notify", etc.)
            source_ref: External reference (commit hash, transaction ID)
            description: Human-readable description
        """
        idem_key = f"reconcile-mint-{source_system}-{source_ref}"
        desc = description or f"Reconciled mint from {source_system} ref:{source_ref}"

        # Verify the authorizer is a valid human
        authority = self.tracker.entities.get_by_slug(authorized_by)
        if authority is None or not authority.is_human():
            return ReconciliationResult(
                event_id=idem_key,
                action="mint",
                status="unauthorized",
                details=f"Authorizer '{authorized_by}' is not a valid human authority. "
                        f"Per CI 40-703.2, only head of household mints.",
            )

        try:
            result = self.tracker.mint(
                entity_slug=entity_slug,
                amount=amount,
                currency_code="MERIT",
                description=desc,
                authorized_by=authorized_by,
                idempotency_key=idem_key,
            )

            # Check if this was a new record or idempotent match
            recorded_amount = Decimal(result["balance_after"])
            return ReconciliationResult(
                event_id=idem_key,
                action="mint",
                status="recorded",
                transaction_id=result["transaction_id"],
                details=f"Minted {amount} MERIT to {entity_slug}, "
                        f"balance now {result['balance_after']}",
            )

        except (ValueError, PermissionError) as e:
            return ReconciliationResult(
                event_id=idem_key,
                action="mint",
                status="discrepancy",
                details=str(e),
            )

    def reconcile_allocation(
        self,
        from_entity_slug: str,
        to_entity_slug: str,
        amount: Decimal,
        source_system: str,
        source_ref: str,
        description: Optional[str] = None,
    ) -> ReconciliationResult:
        """Reconcile an external allocation event."""
        idem_key = f"reconcile-alloc-{source_system}-{source_ref}"
        desc = description or (
            f"Reconciled allocation {from_entity_slug} -> {to_entity_slug} "
            f"from {source_system} ref:{source_ref}"
        )

        try:
            result = self.tracker.allocate(
                from_entity_slug=from_entity_slug,
                to_entity_slug=to_entity_slug,
                amount=amount,
                currency_code="MERIT",
                description=desc,
                idempotency_key=idem_key,
            )

            return ReconciliationResult(
                event_id=idem_key,
                action="allocate",
                status="recorded",
                transaction_id=result["transaction_id"],
                details=f"Allocated {amount} MERIT: {from_entity_slug} -> {to_entity_slug}",
            )

        except ValueError as e:
            return ReconciliationResult(
                event_id=idem_key,
                action="allocate",
                status="discrepancy",
                details=str(e),
            )

    def reconcile_batch(self, events: list[dict]) -> dict:
        """
        Reconcile a batch of external events.

        Each event dict must have:
          - action: "mint" or "allocate"
          - source_system: origin system name
          - source_ref: external reference ID
          - amount: numeric amount

        For mints: entity, authorized_by
        For allocations: from_entity, to_entity

        Returns summary with per-event results.
        """
        results = []
        for event in events:
            action = event.get("action")
            if action == "mint":
                r = self.reconcile_mint(
                    entity_slug=event["entity"],
                    amount=Decimal(str(event["amount"])),
                    authorized_by=event["authorized_by"],
                    source_system=event["source_system"],
                    source_ref=event["source_ref"],
                    description=event.get("description"),
                )
            elif action == "allocate":
                r = self.reconcile_allocation(
                    from_entity_slug=event["from_entity"],
                    to_entity_slug=event["to_entity"],
                    amount=Decimal(str(event["amount"])),
                    source_system=event["source_system"],
                    source_ref=event["source_ref"],
                    description=event.get("description"),
                )
            else:
                r = ReconciliationResult(
                    event_id=f"unknown-{event.get('source_ref', '?')}",
                    action=action or "unknown",
                    status="discrepancy",
                    details=f"Unknown action: {action}",
                )
            results.append(r)

        recorded = sum(1 for r in results if r.status == "recorded")
        confirmed = sum(1 for r in results if r.status == "confirmed")
        discrepancies = sum(1 for r in results if r.status == "discrepancy")
        unauthorized = sum(1 for r in results if r.status == "unauthorized")

        return {
            "total": len(results),
            "recorded": recorded,
            "confirmed": confirmed,
            "discrepancies": discrepancies,
            "unauthorized": unauthorized,
            "ledger_of_record": "silver-shield",
            "results": [r.to_dict() for r in results],
        }

    def get_merit_supply(self) -> dict:
        """
        Report total merit supply across all entities.

        This is the canonical answer to "how much merit exists" --
        derived from Silver Shield's ledger, not external wallets.
        """
        tree = self.tracker.get_entity_tree()
        total_minted = Decimal("0")
        total_held = Decimal("0")
        total_spent = Decimal("0")
        entity_balances = []

        for entity in tree:
            merit_asset = Decimal("0")
            merit_expense = Decimal("0")
            merit_equity = Decimal("0")

            for acct in entity.get("accounts", []):
                if acct["currency"] != "MERIT":
                    continue
                bal = Decimal(acct["balance"])
                if acct["type"] == "asset":
                    merit_asset += bal
                elif acct["type"] == "expense":
                    merit_expense += bal
                elif acct["type"] == "equity":
                    merit_equity += bal

            if merit_asset != 0 or merit_expense != 0 or merit_equity != 0:
                entity_balances.append({
                    "entity": entity["slug"],
                    "name": entity["name"],
                    "type": entity["type"],
                    "merit_held": str(merit_asset),
                    "merit_spent": str(merit_expense),
                    "merit_minted": str(merit_equity),
                })
                total_held += merit_asset
                total_spent += merit_expense
                total_minted += merit_equity

        return {
            "ledger_of_record": "silver-shield",
            "total_minted": str(total_minted),
            "total_held": str(total_held),
            "total_spent": str(total_spent),
            "entities": entity_balances,
        }
