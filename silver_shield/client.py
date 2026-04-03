"""
Silver Shield client -- the integration point for sibling projects.

Any project in the ecosystem imports this to interact with Silver Shield's
ledger. No standalone balance counters, no local wallets.json. Everything
goes through the ledger of record on localhost:5003.

Usage:
    from silver_shield.client import ShieldClient

    shield = ShieldClient()

    # Check if you can afford to send 3 emails
    check = shield.can_afford("auto-agent", "email_send", 3)
    if check["affordable"]:
        shield.merit_spend("auto-agent", "email_send", 3, "Sent briefs to siblings")

    # Check your balance
    balance = shield.merit_balance("auto-agent")

    # Record API token usage
    shield.record_spending("auto-agent", "0.15", "USD", "API tokens: 50k (sonnet)")
"""

import json
import urllib.request
import urllib.error
from typing import Optional


SILVER_SHIELD_URL = "http://localhost:5003"


class ShieldClient:
    """Lightweight HTTP client for Silver Shield's API."""

    def __init__(self, base_url: str = SILVER_SHIELD_URL):
        self.base = base_url

    def _get(self, path: str) -> dict:
        url = f"{self.base}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def _post(self, path: str, data: dict) -> dict:
        url = f"{self.base}{path}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    # ------------------------------------------------------------------
    # Merit operations (most common for sibling projects)
    # ------------------------------------------------------------------

    def merit_balance(self, project_slug: str) -> dict:
        """Get merit balance for a project."""
        return self._get(f"/api/merit/balance/{project_slug}")

    def can_afford(self, project_slug: str, action: str,
                   count: int = 1) -> dict:
        """Check if a project can afford a merit action."""
        return self._get(
            f"/api/merit/can-afford/{project_slug}?action={action}&count={count}")

    def merit_spend(self, project_slug: str, action: str,
                    count: int = 1, description: Optional[str] = None,
                    idempotency_key: Optional[str] = None) -> dict:
        """Record merit spending. Call can_afford first."""
        data = {"project": project_slug, "action": action, "count": count}
        if description:
            data["description"] = description
        if idempotency_key:
            data["idempotency_key"] = idempotency_key
        return self._post("/api/merit/spend", data)

    def merit_costs(self) -> dict:
        """Get the current merit cost table."""
        return self._get("/api/merit/costs")

    # ------------------------------------------------------------------
    # General resource operations
    # ------------------------------------------------------------------

    def record_spending(self, entity_slug: str, amount: str,
                        currency: str, description: str,
                        category: str = "operating",
                        source_system: str = "manual",
                        idempotency_key: Optional[str] = None) -> dict:
        """Record any spending for an entity."""
        data = {
            "entity": entity_slug, "amount": amount,
            "currency": currency, "description": description,
            "category": category, "source_system": source_system,
        }
        if idempotency_key:
            data["idempotency_key"] = idempotency_key
        return self._post("/api/resources/spend", data)

    def get_balance(self, entity_slug: str) -> dict:
        """Get full account summary for an entity."""
        return self._get(f"/api/engine/entity/{entity_slug}")

    def get_accounts(self, entity_slug: str) -> dict:
        """Get all accounts for an entity."""
        return self._get(f"/api/engine/accounts/{entity_slug}")

    # ------------------------------------------------------------------
    # Entity tree
    # ------------------------------------------------------------------

    def entities(self) -> dict:
        """Get the full entity hierarchy."""
        return self._get("/api/engine/entities")

    # ------------------------------------------------------------------
    # Exchange rates
    # ------------------------------------------------------------------

    def get_rate(self, from_currency: str, to_currency: str) -> dict:
        """Get latest exchange rate."""
        return self._get(f"/api/rates/latest/{from_currency}/{to_currency}")
