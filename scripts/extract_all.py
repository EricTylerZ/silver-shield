#!/usr/bin/env python3
"""
Extract transactions from all bank statement PDFs.

Reads config.yaml for account definitions and statement locations,
runs the appropriate parser for each account, and outputs structured
JSON with all transactions categorized.

Usage:
    python scripts/extract_all.py
    python scripts/extract_all.py --config /path/to/config.yaml
    python scripts/extract_all.py --account x1234  # single account
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from silver_shield.config import Config
from silver_shield.extractors import get_extractor
from silver_shield.categorizers.deposits import DepositCategorizer


def main():
    parser = argparse.ArgumentParser(description="Extract transactions from bank statements")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--account", help="Extract only this account ID")
    parser.add_argument("--output", help="Output JSON path (default: output_dir/all_transactions.json)")
    args = parser.parse_args()

    config = Config(args.config)
    categorizer = DepositCategorizer(config)

    accounts = config.all_accounts()
    if args.account:
        accounts = [a for a in accounts if a.id == args.account]
        if not accounts:
            print(f"Account {args.account} not found in config")
            sys.exit(1)

    all_data = {"accounts": {}, "summary": {}}
    total_txns = 0
    total_stmts = 0
    total_mismatches = 0

    for account in accounts:
        stmt_dir = config.statement_path(account)
        if not stmt_dir.exists():
            print(f"  SKIP {account.id}: directory not found ({stmt_dir})")
            continue

        extractor_cls = get_extractor(account.parser)
        extractor = extractor_cls(account.id)

        print(f"Extracting {account.id} ({account.label}) using {account.parser}...")
        statements = extractor.extract_all(str(stmt_dir))

        # Categorize deposits
        for stmt in statements:
            for dep in stmt.deposits:
                categorizer.categorize(dep)

        # Store results
        entity = config.get_entity_for_account(account.id)
        acct_data = {
            "account_id": account.id,
            "entity": entity.name if entity else "Unknown",
            "institution": account.institution,
            "label": account.label,
            "parser": account.parser,
            "statements": [stmt.to_dict() for stmt in statements],
            "totals": {
                "statements": len(statements),
                "deposits": sum(len(s.deposits) for s in statements),
                "withdrawals": sum(len(s.withdrawals) for s in statements),
                "deposit_total": sum(s.deposits_total for s in statements),
                "withdrawal_total": sum(s.withdrawals_total for s in statements),
                "mismatches": sum(len(s.mismatches) for s in statements),
            }
        }
        all_data["accounts"][account.id] = acct_data

        n_stmts = len(statements)
        n_txns = sum(len(s.deposits) + len(s.withdrawals) for s in statements)
        n_mismatch = sum(len(s.mismatches) for s in statements)
        total_stmts += n_stmts
        total_txns += n_txns
        total_mismatches += n_mismatch

        print(f"  {n_stmts} statements, {n_txns} transactions, {n_mismatch} mismatches")

    # Summary
    all_data["summary"] = {
        "total_accounts": len(accounts),
        "total_statements": total_stmts,
        "total_transactions": total_txns,
        "total_mismatches": total_mismatches,
        "accuracy": f"{1 - total_mismatches / max(total_stmts, 1):.1%}",
    }

    # Save
    output_path = args.output or str(config.output_dir / "all_transactions.json")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(all_data, f, indent=2)

    print(f"\nExtraction complete:")
    print(f"  {total_stmts} statements, {total_txns} transactions")
    print(f"  {total_mismatches} mismatches ({all_data['summary']['accuracy']} accuracy)")
    print(f"  Saved to {output_path}")


if __name__ == "__main__":
    main()
