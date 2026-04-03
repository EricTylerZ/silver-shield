#!/usr/bin/env python3
"""
Tax categorization pass — categorizes all transactions against IRS Form 1120
line items with confidence scoring. Generates:
  1. tax_categorized.json — full categorized data
  2. tax_review.html — interactive review page for human verification

Usage:
    python scripts/categorize_taxes.py
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from silver_shield.config import Config
from silver_shield.categorizers.tax_categories import categorize_transaction, ZOSECO_ACCOUNTS


def main():
    config = Config()
    txn_path = config.output_dir / "all_transactions.json"
    if not txn_path.exists():
        print("Run extract_all.py first")
        sys.exit(1)

    with open(txn_path) as f:
        data = json.load(f)

    all_categorized = []
    by_category = defaultdict(list)
    by_confidence = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    transfers_in = defaultdict(float)
    transfers_out = defaultdict(float)

    for acct_id, acct in data.get("accounts", {}).items():
        entity = acct.get("entity", "")
        for stmt in acct.get("statements", []):
            for dep in stmt.get("deposits", []):
                tc = categorize_transaction(dep["description"], acct_id, "deposit", dep["amount"])
                entry = {
                    "date": dep["date"],
                    "account": acct_id,
                    "entity": entity,
                    "type": "deposit",
                    "description": dep["description"],
                    "amount": dep["amount"],
                    "original_category": dep.get("category", ""),
                    "tax_category": tc.category,
                    "form_line": tc.form_line,
                    "confidence": tc.confidence,
                    "is_transfer": tc.is_transfer,
                    "review_note": tc.review_note,
                }
                all_categorized.append(entry)
                by_category[tc.category].append(entry)
                by_confidence[tc.confidence] += 1
                if tc.is_transfer:
                    transfers_in[acct_id] += dep["amount"]

            for wth in stmt.get("withdrawals", []):
                tc = categorize_transaction(wth["description"], acct_id, "withdrawal", wth["amount"])
                entry = {
                    "date": wth["date"],
                    "account": acct_id,
                    "entity": entity,
                    "type": "withdrawal",
                    "description": wth["description"],
                    "amount": wth["amount"],
                    "original_category": wth.get("category", ""),
                    "tax_category": tc.category,
                    "form_line": tc.form_line,
                    "confidence": tc.confidence,
                    "is_transfer": tc.is_transfer,
                    "review_note": tc.review_note,
                }
                all_categorized.append(entry)
                by_category[tc.category].append(entry)
                by_confidence[tc.confidence] += 1
                if tc.is_transfer:
                    transfers_out[acct_id] += wth["amount"]

    all_categorized.sort(key=lambda x: x["date"])

    # Compute Form 1120 summary
    form_summary = defaultdict(lambda: {"deposits": 0, "withdrawals": 0, "count": 0})
    for entry in all_categorized:
        if entry["is_transfer"]:
            continue
        key = f"{entry['form_line']} {entry['tax_category']}"
        if entry["type"] == "deposit":
            form_summary[key]["deposits"] += entry["amount"]
        else:
            form_summary[key]["withdrawals"] += entry["amount"]
        form_summary[key]["count"] += 1

    # Save JSON
    output = {
        "generated": datetime.now().isoformat(),
        "total_transactions": len(all_categorized),
        "confidence_counts": by_confidence,
        "transfer_reconciliation": {
            "transfers_in": dict(transfers_in),
            "transfers_out": dict(transfers_out),
            "net": {acct: transfers_in.get(acct, 0) - transfers_out.get(acct, 0)
                    for acct in ZOSECO_ACCOUNTS},
        },
        "form_1120_summary": {k: v for k, v in sorted(form_summary.items())},
        "transactions": all_categorized,
    }

    json_path = config.output_dir / "tax_categorized.json"
    with open(json_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Generate review HTML
    html_path = config.output_dir / "tax_review.html"
    _generate_review_html(html_path, all_categorized, by_category, by_confidence,
                          form_summary, transfers_in, transfers_out)

    # Print summary
    print("Tax Categorization Complete")
    print("=" * 60)
    print(f"  Total transactions: {len(all_categorized)}")
    print(f"  HIGH confidence:    {by_confidence['HIGH']}")
    print(f"  MEDIUM confidence:  {by_confidence['MEDIUM']}")
    print(f"  LOW confidence:     {by_confidence['LOW']} ← NEEDS REVIEW")
    print()
    print("Form 1120 Summary (excluding internal transfers):")
    for key in sorted(form_summary.keys()):
        v = form_summary[key]
        dep = v["deposits"]
        wth = v["withdrawals"]
        net = dep - wth
        print(f"  {key:40s}  in=${dep:>10,.2f}  out=${wth:>10,.2f}  net=${net:>10,.2f}  ({v['count']} txns)")
    print()
    print(f"  JSON: {json_path}")
    print(f"  Review: {html_path}")


def _generate_review_html(path, all_txns, by_category, by_confidence,
                          form_summary, transfers_in, transfers_out):
    conf_colors = {"HIGH": "#166534", "MEDIUM": "#854d0e", "LOW": "#991b1b"}
    conf_text = {"HIGH": "#bbf7d0", "MEDIUM": "#fef08a", "LOW": "#fecaca"}

    # Category sections
    sections = ""
    for cat in sorted(by_category.keys()):
        txns = by_category[cat]
        total = sum(t["amount"] for t in txns)
        dep_total = sum(t["amount"] for t in txns if t["type"] == "deposit")
        wth_total = sum(t["amount"] for t in txns if t["type"] == "withdrawal")

        confs = defaultdict(int)
        for t in txns:
            confs[t["confidence"]] += 1

        conf_badges = ""
        for c in ["HIGH", "MEDIUM", "LOW"]:
            if confs[c]:
                conf_badges += f'<span style="background:{conf_colors[c]};color:{conf_text[c]};padding:2px 6px;border-radius:3px;font-size:10px;margin-left:4px;">{c}: {confs[c]}</span>'

        form_line = txns[0]["form_line"] if txns else ""
        is_xfer = txns[0]["is_transfer"] if txns else False
        note = txns[0].get("review_note", "")

        rows = ""
        for t in sorted(txns, key=lambda x: x["date"]):
            bg = conf_colors[t["confidence"]]
            fg = conf_text[t["confidence"]]
            type_label = "+" if t["type"] == "deposit" else "-"
            rows += f"""<tr style="border-bottom:1px solid #1e293b;">
                <td style="padding:3px 6px;font-size:11px;color:#94a3b8;">{t['date']}</td>
                <td style="padding:3px 6px;font-size:11px;color:#93c5fd;">{t['account']}</td>
                <td style="padding:3px 6px;font-size:11px;">{type_label}</td>
                <td style="padding:3px 6px;font-size:11px;text-align:right;font-family:monospace;">${t['amount']:,.2f}</td>
                <td style="padding:3px 6px;font-size:10px;color:#94a3b8;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{t['description'][:80]}</td>
                <td style="padding:3px 6px;"><span style="background:{bg};color:{fg};padding:1px 5px;border-radius:3px;font-size:9px;">{t['confidence']}</span></td>
                <td style="padding:3px 6px;font-size:9px;color:#64748b;">{t.get('review_note','')}</td>
            </tr>"""

        xfer_tag = ' <span style="color:#f97316;font-size:10px;">[TRANSFER — eliminated on consolidation]</span>' if is_xfer else ''

        sections += f"""
        <div style="background:#1e293b;border-radius:8px;border:1px solid #334155;margin-bottom:10px;overflow:hidden;">
            <div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'"
                 style="padding:10px 14px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <strong style="font-size:13px;">{cat}</strong>
                    <span style="color:#64748b;font-size:11px;margin-left:8px;">Form {form_line}</span>
                    {xfer_tag}
                    {conf_badges}
                </div>
                <div style="text-align:right;">
                    <span style="color:#22c55e;font-size:12px;font-family:monospace;">+${dep_total:,.2f}</span>
                    <span style="color:#ef4444;font-size:12px;font-family:monospace;margin-left:8px;">-${wth_total:,.2f}</span>
                    <span style="color:#94a3b8;font-size:11px;margin-left:8px;">{len(txns)} txns</span>
                </div>
            </div>
            <div style="display:none;padding:0 14px 10px;">
                {f'<div style="color:#94a3b8;font-size:10px;margin-bottom:6px;">{note}</div>' if note else ''}
                <table style="width:100%;border-collapse:collapse;">{rows}</table>
            </div>
        </div>"""

    # Form 1120 summary table
    form_rows = ""
    total_revenue = 0
    total_expenses = 0
    for key in sorted(form_summary.keys()):
        v = form_summary[key]
        dep = v["deposits"]
        wth = v["withdrawals"]
        if key.startswith("1a") or key.startswith("5") or key.startswith("10"):
            total_revenue += dep
        else:
            total_expenses += wth
        form_rows += f"""<tr style="border-bottom:1px solid #1e293b;">
            <td style="padding:4px 8px;font-size:12px;">{key}</td>
            <td style="padding:4px 8px;text-align:right;font-family:monospace;color:#22c55e;">${dep:,.2f}</td>
            <td style="padding:4px 8px;text-align:right;font-family:monospace;color:#ef4444;">${wth:,.2f}</td>
            <td style="padding:4px 8px;text-align:right;font-family:monospace;">{v['count']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Tax Categorization Review</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;padding:16px;}}
h1{{font-size:1.4rem;margin-bottom:4px;}}
.sub{{color:#64748b;font-size:12px;margin-bottom:16px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-bottom:16px;}}
.stat{{background:#1e293b;border-radius:8px;padding:12px;text-align:center;border:1px solid #334155;}}
.stat .n{{font-size:1.8rem;font-weight:700;}}
.stat .l{{font-size:10px;color:#64748b;text-transform:uppercase;margin-top:2px;}}
</style></head><body>
<h1>Tax Categorization Review</h1>
<p class="sub">IRM Zosso — Case No. 2024DR30400 | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Click any category to expand</p>

<div class="grid">
    <div class="stat"><div class="n">{len(all_txns)}</div><div class="l">Total Txns</div></div>
    <div class="stat"><div class="n" style="color:#22c55e;">{by_confidence['HIGH']}</div><div class="l">High Confidence</div></div>
    <div class="stat"><div class="n" style="color:#eab308;">{by_confidence['MEDIUM']}</div><div class="l">Medium</div></div>
    <div class="stat"><div class="n" style="color:#ef4444;">{by_confidence['LOW']}</div><div class="l">Low — Review</div></div>
    <div class="stat"><div class="n">{len(by_category)}</div><div class="l">Categories</div></div>
    <div class="stat"><div class="n" style="color:#22c55e;">${total_revenue:,.0f}</div><div class="l">Revenue</div></div>
    <div class="stat"><div class="n" style="color:#ef4444;">${total_expenses:,.0f}</div><div class="l">Expenses</div></div>
</div>

<h2 style="font-size:1rem;margin-bottom:8px;">Form 1120 Summary (excluding transfers)</h2>
<div style="background:#1e293b;border-radius:8px;border:1px solid #334155;padding:10px;margin-bottom:16px;overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;">
<tr style="border-bottom:2px solid #334155;"><th style="text-align:left;padding:4px 8px;font-size:11px;color:#64748b;">Line / Category</th><th style="text-align:right;padding:4px 8px;font-size:11px;color:#64748b;">Deposits</th><th style="text-align:right;padding:4px 8px;font-size:11px;color:#64748b;">Withdrawals</th><th style="text-align:right;padding:4px 8px;font-size:11px;color:#64748b;">Txns</th></tr>
{form_rows}
</table>
</div>

<h2 style="font-size:1rem;margin-bottom:8px;">All Categories ({len(by_category)})</h2>
{sections}

</body></html>"""

    with open(path, 'w') as f:
        f.write(html)


if __name__ == "__main__":
    main()
