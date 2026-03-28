#!/usr/bin/env python3
"""
Analyze and categorize all deposits across accounts.

Identifies potential parent/family loans by separating payroll (ACH/direct deposit)
from generic check deposits.

Usage:
    python scripts/analyze_deposits.py
    python scripts/analyze_deposits.py --config /path/to/config.yaml
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from silver_shield.config import Config
from silver_shield.extractors import get_extractor
from silver_shield.categorizers.deposits import DepositCategorizer


def main():
    parser = argparse.ArgumentParser(description="Analyze deposits across all accounts")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--transactions", help="Path to all_transactions.json (from extract_all)")
    args = parser.parse_args()

    config = Config(args.config)
    categorizer = DepositCategorizer(config)

    # Load or extract transaction data
    txn_path = args.transactions or str(config.output_dir / "all_transactions.json")
    if not Path(txn_path).exists():
        print(f"Transaction file not found: {txn_path}")
        print("Run extract_all.py first.")
        sys.exit(1)

    with open(txn_path) as f:
        data = json.load(f)

    print("="*70)
    print("DEPOSIT CATEGORIZATION ANALYSIS")
    print("="*70)

    all_parent_deposits = []
    grand_total = 0

    for acct_id, acct_data in data.get("accounts", {}).items():
        print(f"\n--- {acct_id} ({acct_data.get('label', '')}) ---")

        by_cat = defaultdict(lambda: {"count": 0, "total": 0.0})
        deposits = []

        for stmt in acct_data.get("statements", []):
            for dep in stmt.get("deposits", []):
                from silver_shield.extractors.base import Transaction
                txn = Transaction(
                    date=dep["date"],
                    description=dep["description"],
                    amount=dep["amount"],
                    type="deposit",
                    category=dep.get("category", ""),
                )
                if not txn.category:
                    categorizer.categorize(txn)
                cat = txn.category
                by_cat[cat]["count"] += 1
                by_cat[cat]["total"] += txn.amount
                deposits.append(txn)

                if categorizer.is_possible_parent_debt(txn):
                    all_parent_deposits.append({
                        "account": acct_id,
                        "date": txn.date,
                        "amount": txn.amount,
                        "description": txn.description,
                        "category": cat,
                    })

        for cat in sorted(by_cat.keys()):
            info = by_cat[cat]
            print(f"  {cat}: {info['count']} deposits, ${info['total']:,.2f}")

        acct_total = sum(d.amount for d in deposits)
        grand_total += acct_total
        print(f"  TOTAL: {len(deposits)} deposits, ${acct_total:,.2f}")

    # Parent deposits
    print("\n" + "="*70)
    print("POSSIBLE PARENT/FAMILY DEPOSITS")
    print("="*70)

    all_parent_deposits.sort(key=lambda x: x["date"])
    parent_total = 0
    for dep in all_parent_deposits:
        print(f"  [{dep['account']}] {dep['date']}  ${dep['amount']:>10,.2f}  {dep['description'][:60]}")
        parent_total += dep["amount"]

    print(f"\n  TOTAL: {len(all_parent_deposits)} deposits, ${parent_total:,.2f}")
    print(f"  ({parent_total/grand_total*100:.1f}% of all deposits)" if grand_total else "")

    # Save analysis
    analysis = {
        "parent_deposits": all_parent_deposits,
        "parent_total": parent_total,
        "parent_count": len(all_parent_deposits),
        "grand_deposit_total": grand_total,
    }
    output_path = str(config.output_dir / "deposit_analysis.json")
    with open(output_path, 'w') as f:
        json.dump(analysis, f, indent=2)
    print(f"\nSaved analysis to {output_path}")


if __name__ == "__main__":
    main()
