#!/usr/bin/env python3
"""
Statement Coverage Chart Generator

Builds an HTML dashboard showing which statements have been parsed
per account, per month, per entity. Identifies gaps in coverage.

Usage:
    python scripts/statement_coverage.py
    python scripts/statement_coverage.py --config /path/to/config.yaml
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from silver_shield.config import Config


def month_range(start: str, end: str):
    """Generate YYYY-MM strings from start to end inclusive."""
    s = datetime.strptime(start[:7], "%Y-%m")
    e = datetime.strptime(end[:7], "%Y-%m")
    while s <= e:
        yield s.strftime("%Y-%m")
        if s.month == 12:
            s = s.replace(year=s.year + 1, month=1)
        else:
            s = s.replace(month=s.month + 1)


def main():
    parser = argparse.ArgumentParser(description="Statement coverage chart")
    parser.add_argument("--config", help="Path to config.yaml")
    args = parser.parse_args()

    config = Config(args.config)
    txn_path = config.output_dir / "all_transactions.json"

    if not txn_path.exists():
        print(f"Run extract_all.py first — {txn_path} not found")
        sys.exit(1)

    with open(txn_path) as f:
        data = json.load(f)

    # Build coverage map: account -> {month -> statement_info}
    accounts_info = {}
    global_min = "2099-12"
    global_max = "2000-01"

    for acct_id, acct_data in data["accounts"].items():
        entity = acct_data.get("entity", "Unknown")
        institution = acct_data.get("institution", "")
        label = acct_data.get("label", acct_id)
        stmts = acct_data.get("statements", [])

        coverage = {}
        for stmt in stmts:
            ps = stmt.get("period_start", "")
            pe = stmt.get("period_end", "")
            if not ps or not pe:
                continue

            # Track global range
            if ps[:7] < global_min:
                global_min = ps[:7]
            if pe[:7] > global_max:
                global_max = pe[:7]

            # Mark each month this statement covers
            for m in month_range(ps, pe):
                txn_count = len(stmt.get("deposits", [])) + len(stmt.get("withdrawals", []))
                mismatches = len(stmt.get("mismatches", []))
                opening = stmt.get("opening_balance", 0)
                closing = stmt.get("closing_balance", 0)

                if m not in coverage:
                    coverage[m] = {
                        "files": [],
                        "txn_count": 0,
                        "mismatches": 0,
                        "closing_balance": 0,
                    }
                coverage[m]["files"].append(stmt.get("file", ""))
                coverage[m]["txn_count"] += txn_count
                coverage[m]["mismatches"] += mismatches
                coverage[m]["closing_balance"] = closing

        accounts_info[acct_id] = {
            "entity": entity,
            "institution": institution,
            "label": label,
            "total_stmts": len(stmts),
            "total_txns": sum(
                len(s.get("deposits", [])) + len(s.get("withdrawals", []))
                for s in stmts
            ),
            "coverage": coverage,
        }

    # Generate all months in range
    all_months = list(month_range(global_min, global_max))

    # Group accounts by entity
    entities = defaultdict(list)
    for acct_id, info in accounts_info.items():
        entities[info["entity"]].append((acct_id, info))

    # Build HTML
    html = _build_html(entities, all_months, accounts_info)

    output_path = config.output_dir / "statement_coverage.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(html)

    # Print summary
    print("Statement Coverage Report")
    print("=" * 60)
    total_gaps = 0
    for entity_name, accts in sorted(entities.items()):
        print(f"\n{entity_name}:")
        for acct_id, info in accts:
            covered = len(info["coverage"])
            expected = len(all_months)
            gaps = expected - covered
            total_gaps += gaps
            status = "COMPLETE" if gaps == 0 else f"{gaps} GAPS"
            print(f"  {acct_id} ({info['label']}): {info['total_stmts']} stmts, "
                  f"{info['total_txns']} txns, {covered}/{expected} months [{status}]")

    print(f"\nTotal months in range: {len(all_months)} ({all_months[0]} to {all_months[-1]})")
    print(f"Total gaps across all accounts: {total_gaps}")
    print(f"Output: {output_path}")


def _build_html(entities, all_months, accounts_info):
    # Year boundaries for headers
    years = sorted(set(m[:4] for m in all_months))
    months_per_year = defaultdict(list)
    for m in all_months:
        months_per_year[m[:4]].append(m)

    month_labels = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']

    rows_html = ""

    for entity_name in sorted(entities.keys()):
        accts = entities[entity_name]
        rows_html += f'<tr class="entity-row"><td colspan="{len(all_months) + 4}">{entity_name}</td></tr>\n'

        for acct_id, info in accts:
            cells = ""
            for m in all_months:
                cov = info["coverage"].get(m)
                if cov:
                    txns = cov["txn_count"]
                    mm = cov["mismatches"]
                    bal = cov["closing_balance"]
                    if mm > 0:
                        cls = "mismatch"
                        tip = f"{m}: {txns} txns, {mm} mismatches, ${bal:,.2f}"
                    elif txns > 0:
                        cls = "full"
                        tip = f"{m}: {txns} txns, ${bal:,.2f}"
                    else:
                        cls = "empty"
                        tip = f"{m}: statement found, 0 txns, ${bal:,.2f}"
                    cells += f'<td class="cell {cls}" title="{tip}">{txns if txns else "&middot;"}</td>'
                else:
                    cells += f'<td class="cell gap" title="{m}: NO STATEMENT">&times;</td>'

            total_txns = info["total_txns"]
            total_stmts = info["total_stmts"]
            gaps = sum(1 for m in all_months if m not in info["coverage"])

            rows_html += (
                f'<tr>'
                f'<td class="acct-id">{acct_id}</td>'
                f'<td class="acct-label">{info["institution"]} {info["label"]}</td>'
                f'<td class="acct-stats">{total_stmts}s/{total_txns}t</td>'
                f'<td class="acct-gaps {"has-gaps" if gaps else "no-gaps"}">{gaps} gaps</td>'
                f'{cells}'
                f'</tr>\n'
            )

    # Year/month header
    year_header = '<th></th><th></th><th></th><th></th>'
    month_header = '<th>Acct</th><th>Label</th><th>S/T</th><th>Gaps</th>'
    for yr in years:
        count = len(months_per_year[yr])
        year_header += f'<th colspan="{count}" class="year-header">{yr}</th>'
        for m in months_per_year[yr]:
            mi = int(m[5:7]) - 1
            month_header += f'<th class="month-header">{month_labels[mi]}</th>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Statement Coverage — IRM Zosso</title>
<style>
:root {{ --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #64748b; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, system-ui, monospace; background: var(--bg); color: var(--text); padding: 16px; font-size: 12px; }}
h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
.subtitle {{ color: var(--muted); margin-bottom: 16px; font-size: 0.85rem; }}
table {{ border-collapse: collapse; }}
th, td {{ padding: 3px 5px; text-align: center; white-space: nowrap; }}
.year-header {{ background: #334155; color: #e2e8f0; font-weight: 700; border-bottom: 2px solid #475569; }}
.month-header {{ background: #1e293b; color: var(--muted); font-size: 10px; }}
.entity-row td {{ background: #475569; color: #fff; font-weight: 700; padding: 6px 8px; text-align: left; font-size: 13px; }}
.acct-id {{ text-align: left; font-weight: 600; color: #93c5fd; min-width: 50px; }}
.acct-label {{ text-align: left; color: var(--muted); font-size: 11px; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }}
.acct-stats {{ color: var(--muted); font-size: 10px; }}
.acct-gaps {{ font-size: 10px; font-weight: 600; }}
.has-gaps {{ color: #ef4444; }}
.no-gaps {{ color: #22c55e; }}
.cell {{ width: 22px; height: 22px; font-size: 9px; border: 1px solid #1e293b; cursor: default; }}
.cell.full {{ background: #166534; color: #bbf7d0; }}
.cell.empty {{ background: #1e3a5f; color: #7dd3fc; }}
.cell.mismatch {{ background: #7c2d12; color: #fed7aa; }}
.cell.gap {{ background: #450a0a; color: #fca5a5; font-weight: 700; }}
.legend {{ margin-top: 12px; display: flex; gap: 16px; font-size: 11px; color: var(--muted); }}
.legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
.legend .swatch {{ width: 14px; height: 14px; border-radius: 2px; display: inline-block; }}
@media print {{
  body {{ background: #fff; color: #000; font-size: 10px; }}
  .cell.full {{ background: #c6f6d5; color: #000; }}
  .cell.gap {{ background: #fed7d7; color: #000; }}
}}
</style>
</head>
<body>
<h1>Statement Coverage Chart</h1>
<p class="subtitle">IRM Zosso — Case No. 2024DR30400 | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | {len(all_months)} months ({all_months[0]} to {all_months[-1]})</p>

<div style="overflow-x: auto;">
<table>
<thead>
<tr>{year_header}</tr>
<tr>{month_header}</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>

<div class="legend">
  <span><span class="swatch" style="background:#166534;"></span> Parsed (with txns)</span>
  <span><span class="swatch" style="background:#1e3a5f;"></span> Statement found (0 txns)</span>
  <span><span class="swatch" style="background:#7c2d12;"></span> Mismatch</span>
  <span><span class="swatch" style="background:#450a0a;"></span> Gap (no statement)</span>
</div>

<p style="color: var(--muted); margin-top: 8px; font-size: 11px;">Hover cells for details. S/T = statements/transactions.</p>
</body>
</html>"""


if __name__ == "__main__":
    main()
