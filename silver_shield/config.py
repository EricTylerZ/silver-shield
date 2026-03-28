"""
Configuration loader for Silver Shield.

All file paths and entity mappings come from config.yaml.
No personal data is hardcoded anywhere in the codebase.
"""

import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Account:
    """A single bank/financial account."""
    id: str
    institution: str
    type: str  # checking, savings, credit, brokerage, crypto
    label: str
    parser: str  # centier, usaa, generic, ocr
    statement_dir: str

    @property
    def short_id(self) -> str:
        """Return last 4 digits for display."""
        return self.id[-4:] if len(self.id) >= 4 else self.id


@dataclass
class Entity:
    """A legal entity (person or business)."""
    name: str
    type: str  # personal, business
    accounts: list[Account] = field(default_factory=list)


@dataclass
class CategorizationRule:
    """A deposit categorization rule."""
    pattern: str
    category: str
    flags: str = ""

    def matches(self, description: str) -> bool:
        return bool(re.search(self.pattern, description, re.IGNORECASE))


@dataclass
class DeficiencyItem:
    """A deficiency letter item to track."""
    id: int
    name: str
    description: str
    status: str = "missing"  # complete, partial, missing
    percent: int = 0
    notes: str = ""


@dataclass
class ExcelFormat:
    """Excel formatting conventions."""
    input_color: str = "0000FF"
    formula_color: str = "000000"
    crossref_color: str = "008000"
    external_color: str = "FF0000"
    attention_bg: str = "FFFF00"
    header_bg: str = "333333"
    header_fg: str = "FFFFFF"
    currency_format: str = '$#,##0.00;($#,##0.00);"-"'


class Config:
    """Silver Shield configuration loaded from YAML."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = self._find_config()
        self.config_path = Path(config_path)
        self._raw = self._load()
        self._parse()

    def _find_config(self) -> str:
        """Search for config.yaml in standard locations."""
        candidates = [
            Path.cwd() / "config.yaml",
            Path.cwd().parent / "config.yaml",
            Path.home() / ".silver-shield" / "config.yaml",
        ]
        env_path = os.environ.get("SILVER_SHIELD_CONFIG")
        if env_path:
            candidates.insert(0, Path(env_path))

        for p in candidates:
            if p.exists():
                return str(p)

        raise FileNotFoundError(
            "No config.yaml found. Copy config.yaml.example to config.yaml "
            "and set your paths. Or set SILVER_SHIELD_CONFIG env var."
        )

    def _load(self) -> dict:
        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _parse(self):
        self.case_name = self._raw.get("case", {}).get("name", "Untitled Case")
        self.case_number = self._raw.get("case", {}).get("number", "")
        self.jurisdiction = self._raw.get("case", {}).get("jurisdiction", "")

        self.data_dir = Path(self._raw["data_dir"])
        self.output_dir = Path(self._raw["output_dir"])
        self.ledger_file = self._raw.get("ledger_file", "Financial Ledger.xlsx")
        self.tracker_file = self._raw.get("tracker_file", "Deficiency_Response_Tracker.html")

        # Entities
        self.entities: list[Entity] = []
        for e in self._raw.get("entities", []):
            accounts = [
                Account(
                    id=a["id"],
                    institution=a.get("institution", ""),
                    type=a.get("type", "checking"),
                    label=a.get("label", a["id"]),
                    parser=a.get("parser", "generic"),
                    statement_dir=a.get("statement_dir", a["id"]),
                )
                for a in e.get("accounts", [])
            ]
            self.entities.append(Entity(name=e["name"], type=e["type"], accounts=accounts))

        # Categorization rules
        self.categorization_rules: list[CategorizationRule] = []
        for r in self._raw.get("categorization_rules", []):
            self.categorization_rules.append(CategorizationRule(
                pattern=r["pattern"],
                category=r["category"],
                flags=r.get("flags", ""),
            ))

        # Parent debt categories
        self.parent_debt_categories = self._raw.get("parent_debt_categories", ["GENERIC_DEPOSIT"])

        # Deficiency items
        self.deficiency_items: list[DeficiencyItem] = []
        for item in self._raw.get("deficiency_items", []):
            self.deficiency_items.append(DeficiencyItem(
                id=item["id"],
                name=item["name"],
                description=item.get("description", ""),
            ))

        # Excel formatting
        fmt = self._raw.get("excel_formatting", {})
        self.excel_format = ExcelFormat(**{k: v for k, v in fmt.items() if k in ExcelFormat.__dataclass_fields__})

    @property
    def ledger_path(self) -> Path:
        return self.output_dir / self.ledger_file

    @property
    def tracker_path(self) -> Path:
        return self.output_dir / self.tracker_file

    def get_entity(self, name: str) -> Optional[Entity]:
        for e in self.entities:
            if e.name.lower() == name.lower():
                return e
        return None

    def get_account(self, account_id: str) -> Optional[Account]:
        for e in self.entities:
            for a in e.accounts:
                if a.id == account_id:
                    return a
        return None

    def get_entity_for_account(self, account_id: str) -> Optional[Entity]:
        for e in self.entities:
            for a in e.accounts:
                if a.id == account_id:
                    return e
        return None

    def statement_path(self, account: Account) -> Path:
        return self.data_dir / account.statement_dir

    def all_accounts(self) -> list[Account]:
        return [a for e in self.entities for a in e.accounts]

    def personal_entities(self) -> list[Entity]:
        return [e for e in self.entities if e.type == "personal"]

    def business_entities(self) -> list[Entity]:
        return [e for e in self.entities if e.type == "business"]
