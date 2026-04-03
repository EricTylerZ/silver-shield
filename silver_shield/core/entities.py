"""
Entity hierarchy management.

Enforces the core distributist constraint: every entity chain
terminates at a human. Agents serve people. Agents may manage
sub-agents. There is always a human at the top.
"""

from typing import Optional

from .models import Entity, EntityType
from ..storage.base import StorageBackend


class EntityManager:
    """Manages the entity hierarchy."""

    def __init__(self, store: StorageBackend):
        self.store = store

    def create(self, name: str, slug: str, entity_type: EntityType,
               parent_id: Optional[str] = None,
               metadata: Optional[dict] = None) -> Entity:
        """
        Create an entity in the hierarchy.

        If entity_type is PERSON and parent_id is None, this is the root human.
        All other entities must have a parent, and the chain must terminate
        at a person.
        """
        if entity_type == EntityType.PERSON and parent_id is None:
            # Root human -- human_authority is self
            entity = Entity(
                slug=slug, name=name, entity_type=entity_type,
                parent_id=None, human_authority=None,
                metadata=metadata or {},
            )
            entity.human_authority = entity.id
            self.store.create_entity(entity)
            return entity

        if parent_id is None:
            raise ValueError(
                f"Non-person entity '{name}' must have a parent. "
                "Only the root human can have no parent."
            )

        # Validate parent exists
        parent = self.store.get_entity(parent_id)
        if parent is None:
            raise ValueError(f"Parent entity '{parent_id}' not found")

        # Walk to root to find human authority
        human_authority = self._find_human_authority(parent)
        if human_authority is None:
            raise ValueError(
                f"Entity chain from parent '{parent.name}' does not "
                "terminate at a human. An agent unto itself is not acceptable."
            )

        entity = Entity(
            slug=slug, name=name, entity_type=entity_type,
            parent_id=parent_id, human_authority=human_authority,
            metadata=metadata or {},
        )
        self.store.create_entity(entity)
        return entity

    def get(self, entity_id: str) -> Optional[Entity]:
        return self.store.get_entity(entity_id)

    def get_by_slug(self, slug: str) -> Optional[Entity]:
        return self.store.get_entity_by_slug(slug)

    def get_children(self, entity_id: str) -> list[Entity]:
        return self.store.list_entities(parent_id=entity_id)

    def get_subtree(self, entity_id: str) -> list[Entity]:
        """Get all descendants of an entity (breadth-first)."""
        result = []
        queue = [entity_id]
        while queue:
            current_id = queue.pop(0)
            children = self.store.list_entities(parent_id=current_id)
            result.extend(children)
            queue.extend(c.id for c in children)
        return result

    def list_all(self) -> list[Entity]:
        return self.store.list_entities()

    def validate_human_authority(self, entity_id: str) -> bool:
        """Verify the chain from entity_id to root terminates at a person."""
        entity = self.store.get_entity(entity_id)
        if entity is None:
            return False
        return self._find_human_authority(entity) is not None

    def _find_human_authority(self, entity: Entity) -> Optional[str]:
        """Walk up the tree to find the root human. Returns their id or None."""
        visited = set()
        current = entity
        while current is not None:
            if current.id in visited:
                return None  # cycle detected
            visited.add(current.id)
            if current.is_human() and current.is_root():
                return current.id
            if current.parent_id is None:
                # Non-human root -- invalid
                return current.human_authority if current.is_human() else None
            current = self.store.get_entity(current.parent_id)
        return None
