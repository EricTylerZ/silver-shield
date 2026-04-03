"""
Ecosystem bootstrapper.

Reads the project registry from community-shield at :4222 and creates
corresponding entities in Silver Shield's hierarchy. This is how the
entity tree gets populated -- Silver Shield is the gatekeeper, and
every project that wants accounting must exist here.

Pattern:
  Root person (human authority)
    -> Each project becomes an entity (PROJECT or AGENT type)
    -> Each gets a MERIT asset account + USD asset account
    -> Head of household mints into root treasury
    -> Allocations flow from treasury to projects
"""

import urllib.request
import json
from decimal import Decimal
from typing import Optional

from ..core.models import EntityType, AccountType
from ..resources.tracker import ResourceTracker


# Map community-shield dominion types to Silver Shield entity types
DOMINION_TO_ENTITY = {
    "livestock": EntityType.AGENT,
    "bird": EntityType.AGENT,
    "fish": EntityType.AGENT,
    "creeping_thing": EntityType.AGENT,
    "substrate": EntityType.PROJECT,
    "hybrid": EntityType.PROJECT,
}

COMMUNITY_SHIELD_URL = "http://localhost:4222"


class EcosystemBootstrap:
    """Bootstrap Silver Shield's entity tree from the ecosystem registry."""

    def __init__(self, tracker: ResourceTracker):
        self.tracker = tracker

    def fetch_registry(self) -> list[dict]:
        """Fetch project list from community-shield."""
        url = f"{COMMUNITY_SHIELD_URL}/api/projects"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def bootstrap(self, human_name: str, human_slug: str,
                  skip_self: bool = True) -> dict:
        """
        Create the full entity hierarchy.

        1. Create root person (human authority)
        2. Fetch ecosystem registry
        3. Create entity for each project under root
        4. Create MERIT + USD asset accounts for each

        Returns summary of what was created.
        """
        # Step 1: root human (idempotent -- skip if exists)
        root = self.tracker.entities.get_by_slug(human_slug)
        if root is None:
            root = self.tracker.entities.create(
                human_name, human_slug, EntityType.PERSON)

        # Step 2: fetch registry
        projects = self.fetch_registry()

        created = []
        skipped = []

        for proj in projects:
            slug = proj["id"]

            if skip_self and slug == "silver-shield":
                # Silver Shield doesn't need to be its own accounting client,
                # but it does need an entity for receiving allocations
                pass  # still create it below

            # Check if already exists
            existing = self.tracker.entities.get_by_slug(slug)
            if existing:
                skipped.append(slug)
                continue

            # Determine entity type
            dominion = proj.get("dominion_type", "").lower()
            entity_type = DOMINION_TO_ENTITY.get(dominion, EntityType.PROJECT)

            # Create entity under root
            entity = self.tracker.entities.create(
                name=proj.get("name", slug),
                slug=slug,
                entity_type=entity_type,
                parent_id=root.id,
                metadata={
                    "port": proj.get("port"),
                    "dominion_type": dominion,
                    "description": proj.get("description", ""),
                },
            )

            # Create default accounts: MERIT asset + USD asset
            self.tracker.accounts.open(
                entity.id, "MERIT", AccountType.ASSET,
                f"{slug} merit treasury")
            self.tracker.accounts.open(
                entity.id, "USD", AccountType.ASSET,
                f"{slug} USD treasury")

            created.append(slug)

        # Ensure root has treasury accounts too
        if not self.tracker._find_account(root.id, "MERIT", AccountType.ASSET):
            self.tracker.accounts.open(
                root.id, "MERIT", AccountType.ASSET, "household merit treasury")
        if not self.tracker._find_account(root.id, "USD", AccountType.ASSET):
            self.tracker.accounts.open(
                root.id, "USD", AccountType.ASSET, "household USD treasury")
        if not self.tracker._find_account(root.id, "MERIT", AccountType.EQUITY):
            self.tracker.accounts.open(
                root.id, "MERIT", AccountType.EQUITY, "merit minted",
                metadata={"category": "mint"})
        if not self.tracker._find_account(root.id, "USD", AccountType.EQUITY):
            self.tracker.accounts.open(
                root.id, "USD", AccountType.EQUITY, "USD equity",
                metadata={"category": "mint"})

        return {
            "root": {"name": human_name, "slug": human_slug, "id": root.id},
            "created": created,
            "skipped": skipped,
            "total_entities": len(created) + len(skipped) + 1,
        }

    def mint_and_allocate(
        self,
        human_slug: str,
        merit_amount: Decimal,
        per_project_merit: Optional[Decimal] = None,
        idempotency_prefix: str = "bootstrap",
    ) -> dict:
        """
        Mint merit into the household treasury and allocate to all projects.

        If per_project_merit is None, divides equally.
        """
        # Mint into root treasury
        mint_result = self.tracker.mint(
            human_slug, merit_amount, "MERIT",
            "Household merit mint -- ecosystem bootstrap",
            authorized_by=human_slug,
            idempotency_key=f"{idempotency_prefix}-mint",
        )

        # Get all child entities
        root = self.tracker.entities.get_by_slug(human_slug)
        children = self.tracker.entities.get_children(root.id)

        if not children:
            return {"minted": mint_result, "allocations": []}

        per_project = per_project_merit or (merit_amount // len(children))
        allocations = []

        for child in children:
            if per_project <= 0:
                break
            try:
                result = self.tracker.allocate(
                    human_slug, child.slug, per_project, "MERIT",
                    f"Bootstrap allocation to {child.slug}",
                    idempotency_key=f"{idempotency_prefix}-alloc-{child.slug}",
                )
                allocations.append(result)
            except ValueError:
                # Entity might not have a MERIT account yet
                pass

        return {
            "minted": mint_result,
            "allocations": allocations,
            "per_project": str(per_project),
        }
