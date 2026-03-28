#!/usr/bin/env python3
"""
Build the financial ledger Excel workbook.

Creates a multi-sheet workbook from config.yaml entity definitions.
Run extract_all.py first to generate transaction data.

Usage:
    python scripts/build_ledger.py
    python scripts/build_ledger.py --config /path/to/config.yaml
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from silver_shield.config import Config
from silver_shield.ledger.builder import LedgerBuilder
from silver_shield.compliance.ci42 import CI42Checker


def main():
    parser = argparse.ArgumentParser(description="Build financial ledger workbook")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--output", help="Output xlsx path")
    args = parser.parse_args()

    config = Config(args.config)
    builder = LedgerBuilder(config)

    print(f"Building ledger for {config.case_name}...")
    print(f"  Entities: {len(config.entities)}")
    print(f"  Accounts: {len(config.all_accounts())}")

    wb = builder.build()
    output = builder.save(args.output)
    print(f"  Sheets: {', '.join(wb.sheetnames)}")
    print(f"  Saved to {output}")

    # Run compliance checks
    print("\nRunning CI 42 compliance checks...")
    checker = CI42Checker(config)
    results = checker.run_all(ledger_path=output)
    print(checker.summary())


if __name__ == "__main__":
    main()
