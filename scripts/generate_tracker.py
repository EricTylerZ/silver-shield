#!/usr/bin/env python3
"""
Generate the deficiency response tracker HTML dashboard.

Usage:
    python scripts/generate_tracker.py
    python scripts/generate_tracker.py --config /path/to/config.yaml
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from silver_shield.config import Config
from silver_shield.compliance.deficiency import DeficiencyTracker


def main():
    parser = argparse.ArgumentParser(description="Generate deficiency tracker dashboard")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--output", help="Output HTML path")
    args = parser.parse_args()

    config = Config(args.config)
    tracker = DeficiencyTracker(config)

    # Default: all items start as missing
    # User updates status via config or programmatically
    print(f"Generating tracker for {config.case_name}...")
    print(f"  {len(config.deficiency_items)} items configured")

    output = tracker.save_html(args.output)
    print(f"  Overall: {tracker.overall_percent}%")
    print(f"  Complete: {tracker.complete_count}, Partial: {tracker.partial_count}, Missing: {tracker.missing_count}")
    print(f"  Saved to {output}")


if __name__ == "__main__":
    main()
