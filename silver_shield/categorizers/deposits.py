"""
Deposit categorization engine.

Classifies bank deposits into categories based on description keywords.
Rules are loaded from config.yaml so users can customize for their situation.

Default hierarchy: crypto > payroll > business > transfer > interest > refund > generic deposit.

Key insight for family law: payroll appears as ACH/DIRECT DEPOSIT with employer name,
while parent loans (check deposits) appear as generic "DEPOSIT" with no description.
"""

import re
from typing import Optional

from ..config import Config, CategorizationRule
from ..extractors.base import Transaction


# Default rules if none in config
DEFAULT_RULES = [
    CategorizationRule("COINBASE|KRAKEN|CRYPTO", "CRYPTO_EXCHANGE"),
    CategorizationRule("DIRECT DEP|DIR DEP|PAYROLL|GUSTO|SALARY|WAGES", "PAYROLL/INCOME"),
    CategorizationRule("STRIPE", "BUSINESS_INCOME"),
    CategorizationRule("XFER|TRANSFER|TRNSFR|WIRE|EXT-INTRNT", "TRANSFER"),
    CategorizationRule("ZELLE", "ZELLE"),
    CategorizationRule("INTEREST|IOD", "INTEREST"),
    CategorizationRule("RTN|RETURN|REFUND|REVERSAL", "RETURN/REFUND"),
    CategorizationRule("SCHWAB|MONEYLINK", "BROKERAGE_TRANSFER"),
    CategorizationRule("VENMO|CASHAPP|CASH APP|PAYPAL", "PEER_PAYMENT"),
    CategorizationRule(r"^DEPOSIT$|^DEPOSIT\s*$|^DEPOSIT@", "GENERIC_DEPOSIT", "possible_parent_debt"),
]


class DepositCategorizer:
    """Categorizes deposit transactions using configurable rules."""

    def __init__(self, config: Optional[Config] = None):
        if config and config.categorization_rules:
            self.rules = config.categorization_rules
        else:
            self.rules = DEFAULT_RULES

        self.parent_categories = (
            config.parent_debt_categories if config
            else ["GENERIC_DEPOSIT", "CASH_DEPOSIT", "CHECK_DEPOSIT"]
        )

    def categorize(self, transaction: Transaction) -> str:
        """Assign a category to a deposit transaction."""
        desc = transaction.description.upper().strip()

        for rule in self.rules:
            if rule.matches(desc):
                transaction.category = rule.category
                return rule.category

        transaction.category = "OTHER"
        return "OTHER"

    def categorize_all(self, transactions: list[Transaction]) -> dict[str, list[Transaction]]:
        """Categorize a list of transactions, return grouped by category."""
        grouped: dict[str, list[Transaction]] = {}
        for txn in transactions:
            if txn.type == 'deposit':
                cat = self.categorize(txn)
                if cat not in grouped:
                    grouped[cat] = []
                grouped[cat].append(txn)
        return grouped

    def is_possible_parent_debt(self, transaction: Transaction) -> bool:
        """Check if a deposit might be a parent/family loan."""
        if not transaction.category:
            self.categorize(transaction)
        return transaction.category in self.parent_categories

    def identify_parent_deposits(self, transactions: list[Transaction]) -> list[Transaction]:
        """Filter transactions to only those flagged as possible parent debt."""
        return [t for t in transactions if self.is_possible_parent_debt(t)]

    def summary(self, transactions: list[Transaction]) -> dict:
        """Generate categorization summary statistics."""
        grouped = self.categorize_all(transactions)
        result = {}
        for cat, txns in sorted(grouped.items()):
            result[cat] = {
                "count": len(txns),
                "total": sum(t.amount for t in txns),
                "is_parent_candidate": cat in self.parent_categories,
            }
        return result
