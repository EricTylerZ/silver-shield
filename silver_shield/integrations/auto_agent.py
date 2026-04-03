"""
Auto-Agent resource bridge.

Records resource consumption (API tokens, compute costs) for projects
managed by auto-agent. Enables CI 90-001.3 (resource awareness before
proposals) by giving auto-agent a balance check before spending.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from ..resources.tracker import ResourceTracker


class AutoAgentBridge:
    """Bridge between auto-agent and Silver Shield's resource tracking."""

    def __init__(self, tracker: ResourceTracker):
        self.tracker = tracker

    def record_token_usage(
        self,
        project_slug: str,
        tokens: int,
        cost_usd: Decimal,
        model: str = "unknown",
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Record API token consumption for a project.

        Debits the project's USD expense account for the dollar cost.
        """
        desc = description or f"API tokens: {tokens:,} ({model})"

        return self.tracker.record_spending(
            entity_slug=project_slug,
            amount=cost_usd,
            currency_code="USD",
            description=desc,
            category="api_tokens",
            source_system="auto_agent",
            idempotency_key=idempotency_key,
        )

    def get_resource_summary(self, project_slug: str) -> dict:
        """
        Get resource consumption summary for a project.

        Returns balances across all currencies + recent entries.
        """
        summary = self.tracker.get_entity_summary(project_slug)
        entries = self.tracker.get_entries(project_slug, limit=20)

        return {
            **summary,
            "recent_entries": entries,
        }

    def check_budget(self, project_slug: str, currency_code: str,
                     proposed_amount: Decimal) -> dict:
        """
        Check if a project can afford a proposed expenditure.

        Supports CI 90-001.3: resource awareness before proposals.
        """
        balance = self.tracker.get_balance(project_slug, currency_code)
        affordable = balance >= proposed_amount

        return {
            "entity": project_slug,
            "currency": currency_code,
            "current_balance": str(balance),
            "proposed_amount": str(proposed_amount),
            "affordable": affordable,
            "remaining_after": str(balance - proposed_amount) if affordable else "0",
        }

    def fund_project(
        self,
        treasury_slug: str,
        project_slug: str,
        amount: Decimal,
        currency_code: str,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Allocate funds from treasury to a project."""
        desc = description or f"Budget allocation to {project_slug}"
        return self.tracker.allocate(
            from_entity_slug=treasury_slug,
            to_entity_slug=project_slug,
            amount=amount,
            currency_code=currency_code,
            description=desc,
            idempotency_key=idempotency_key,
        )
