"""
Base extractor classes and data models for bank statement parsing.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Transaction:
    """A single financial transaction."""
    date: str           # YYYY-MM-DD
    description: str
    amount: float
    type: str = ""      # deposit, withdrawal, check, transfer
    category: str = ""  # Set by categorizer
    balance: float = 0  # Running balance if available


@dataclass
class Statement:
    """A single bank statement with extracted data."""
    file_name: str
    account_id: str
    period_start: str   # YYYY-MM-DD
    period_end: str     # YYYY-MM-DD
    opening_balance: float = 0
    closing_balance: float = 0
    deposits_total: float = 0
    withdrawals_total: float = 0
    deposits: list[Transaction] = field(default_factory=list)
    withdrawals: list[Transaction] = field(default_factory=list)
    all_transactions: list[Transaction] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)

    @property
    def extracted_deposit_total(self) -> float:
        return sum(d.amount for d in self.deposits)

    @property
    def extracted_withdrawal_total(self) -> float:
        return sum(w.amount for w in self.withdrawals)

    @property
    def deposit_accuracy(self) -> float:
        if self.deposits_total == 0:
            return 1.0 if self.extracted_deposit_total == 0 else 0.0
        return 1.0 - abs(self.deposits_total - self.extracted_deposit_total) / self.deposits_total

    def to_dict(self) -> dict:
        return {
            "file": self.file_name,
            "account_id": self.account_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "opening_balance": self.opening_balance,
            "closing_balance": self.closing_balance,
            "deposits_total": self.deposits_total,
            "withdrawals_total": self.withdrawals_total,
            "deposits": [
                {"date": d.date, "description": d.description, "amount": d.amount,
                 "category": d.category} for d in self.deposits
            ],
            "withdrawals": [
                {"date": w.date, "description": w.description, "amount": w.amount}
                for w in self.withdrawals
            ],
            "mismatches": self.mismatches,
        }


class StatementRegistry:
    """
    Tracks which statements have been ingested to prevent duplicates.

    Registry file: JSON mapping statement fingerprint -> metadata.
    Fingerprint = sha256(account_id + period_start + period_end).
    """

    def __init__(self, registry_path: str = None):
        self.path = Path(registry_path) if registry_path else None
        self.entries: dict[str, dict] = {}
        if self.path and self.path.exists():
            with open(self.path) as f:
                self.entries = json.load(f)

    @staticmethod
    def fingerprint(account_id: str, period_start: str, period_end: str) -> str:
        key = f"{account_id}|{period_start}|{period_end}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def is_duplicate(self, stmt: 'Statement') -> bool:
        fp = self.fingerprint(stmt.account_id, stmt.period_start, stmt.period_end)
        return fp in self.entries

    def register(self, stmt: 'Statement', source_file: str):
        fp = self.fingerprint(stmt.account_id, stmt.period_start, stmt.period_end)
        self.entries[fp] = {
            "account_id": stmt.account_id,
            "period_start": stmt.period_start,
            "period_end": stmt.period_end,
            "source_file": source_file,
            "transactions": len(stmt.all_transactions),
            "deposits_total": stmt.deposits_total,
            "withdrawals_total": stmt.withdrawals_total,
            "opening_balance": stmt.opening_balance,
            "closing_balance": stmt.closing_balance,
            "ingested_at": datetime.now().isoformat(),
        }

    def save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, 'w') as f:
                json.dump(self.entries, f, indent=2)

    def summary(self) -> str:
        by_account: dict[str, int] = {}
        for e in self.entries.values():
            acct = e.get("account_id", "?")
            by_account[acct] = by_account.get(acct, 0) + 1
        lines = [f"Statement Registry: {len(self.entries)} statements"]
        for acct, count in sorted(by_account.items()):
            lines.append(f"  {acct}: {count} statements")
        return "\n".join(lines)


class BaseExtractor:
    """Base class for bank statement extractors."""

    def __init__(self, account_id: str, registry: StatementRegistry = None):
        self.account_id = account_id
        self.registry = registry

    def extract(self, pdf_path: str) -> Optional[Statement]:
        """Extract transactions from a single PDF. Override in subclasses."""
        raise NotImplementedError

    def extract_all(self, directory: str, file_pattern: str = "*.pdf") -> list[Statement]:
        """Extract from all PDFs in a directory, skipping duplicates."""
        pdf_dir = Path(directory)
        statements = []
        skipped = 0
        for pdf in sorted(pdf_dir.glob(file_pattern)):
            result = self.extract(str(pdf))
            if result:
                if self.registry and self.registry.is_duplicate(result):
                    skipped += 1
                    continue
                if self.registry:
                    self.registry.register(result, str(pdf))
                statements.append(result)
        if skipped:
            print(f"    (skipped {skipped} duplicate statements)")
        return statements

    def validate_statement(self, stmt: Statement) -> list[str]:
        """Check extracted totals against statement totals."""
        issues = []
        dep_diff = abs(stmt.deposits_total - stmt.extracted_deposit_total)
        if dep_diff > 0.02 and stmt.deposits_total > 0:
            issues.append(
                f"Deposit mismatch: statement={stmt.deposits_total:.2f}, "
                f"extracted={stmt.extracted_deposit_total:.2f}, diff={dep_diff:.2f}"
            )
        wth_diff = abs(stmt.withdrawals_total - stmt.extracted_withdrawal_total)
        if wth_diff > 0.02 and stmt.withdrawals_total > 0:
            issues.append(
                f"Withdrawal mismatch: statement={stmt.withdrawals_total:.2f}, "
                f"extracted={stmt.extracted_withdrawal_total:.2f}, diff={wth_diff:.2f}"
            )
        stmt.mismatches = issues
        return issues
