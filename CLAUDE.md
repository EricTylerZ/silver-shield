# Silver Shield -- Financial Bookkeeping Armor

## Who is this for?

Silver Shield is a bookkeeping tool for individuals navigating family law discovery, small business financial reporting, or personal financial organization. It was built to handle the overwhelming volume of bank statements, transaction extraction, entity separation, and compliance tracking required by Rule 121 deficiency letters and similar financial discovery processes.

It is designed to be operated by Claude Code or any AI agent under human supervision.

## What does this codebase do?

Silver Shield automates the painful parts of financial discovery:

1. **Statement Extraction** -- Parses bank statement PDFs (both text-based and image/OCR) into structured JSON transactions
2. **Transaction Categorization** -- Classifies deposits as payroll, business income, crypto, transfers, peer payments, or generic deposits (potential parent loans)
3. **Entity Separation** -- Maps accounts to legal entities (personal, business entities) based on account holder names from actual statement headers
4. **Ledger Generation** -- Builds Excel workbooks with P&L statements, general ledgers, account summaries, parent debt tracking, and personal financial statements
5. **Compliance Tracking** -- Generates HTML dashboards tracking completion of deficiency letter items
6. **Parent Debt Identification** -- Distinguishes payroll (ACH/direct deposit) from check deposits (generic "DEPOSIT" entries) to trace unsecured family loans

## Architecture

```
silver_shield/
  config.py         -- Config loader (YAML-driven, no hardcoded paths)
  extractors/       -- Bank statement parsers (Centier, USAA, Coinbase, generic OCR)
  categorizers/     -- Deposit and transaction classification
  ledger/           -- Excel workbook builder with openpyxl
  compliance/       -- CI 42 series audit checks + deficiency tracking
  reports/          -- HTML dashboard and summary report generators
scripts/            -- CLI entry points for extraction, ledger building, analysis
templates/          -- Empty ledger template, dashboard HTML template
data/               -- Continuity binder (gitignored: user data goes here locally)
config.yaml.example -- Sample configuration (copy to config.yaml, set your paths)
```

## Config-driven paths

**No personal financial data lives in this repository.** All file paths are configured via `config.yaml`:

```yaml
data_dir: /path/to/your/bank/statements
output_dir: /path/to/your/output
entities:
  - name: "Your Name"
    type: personal
    accounts: [x1234, x5678]
  - name: "Your Business LLC"
    type: business
    accounts: [x9012]
```

## Current priorities

1. Generalize extraction pipeline for any Centier or USAA statement set
2. Make ledger builder entity-aware from config (not hardcoded account mappings)
3. Parent debt identification as a reusable pattern for any "check deposit vs direct deposit" separation
4. Deficiency tracker as a generic compliance checklist tool

## Rules and constraints

- **Never commit PII.** No account numbers, names, balances, or transaction data in the repo.
- **Blue/Black/Green convention.** Blue text = hardcoded inputs. Black = formulas/data. Green = cross-sheet links. Yellow background = needs attention.
- **Zero formula errors.** Every Excel output must pass recalc verification with 0 errors.
- **Subsidiarity.** Automate extraction and categorization. Human reviews before legal assertion.
- **Sabbath.** No automated batch runs on Sunday.
- **Double-entry integrity.** Every transaction in the General Ledger must balance to statement totals.

## Key files

| File | Purpose |
|------|---------|
| `silver_shield/config.py` | YAML config loader, path resolution |
| `silver_shield/extractors/centier.py` | Centier bank statement parser (columnar format) |
| `silver_shield/extractors/usaa.py` | USAA statement parser (multi-line transactions) |
| `silver_shield/extractors/ocr.py` | Image-based PDF extraction via pdfplumber + tesseract |
| `silver_shield/categorizers/deposits.py` | Deposit classification engine |
| `silver_shield/ledger/builder.py` | Excel workbook generator |
| `silver_shield/ledger/parent_debt.py` | Parent loan identification logic |
| `silver_shield/compliance/ci42.py` | CI 42 audit compliance checks |
| `silver_shield/reports/tracker.py` | HTML deficiency tracker generator |
| `scripts/extract_all.py` | CLI: extract transactions from all statements |
| `scripts/build_ledger.py` | CLI: generate Excel ledger from extracted data |
| `scripts/analyze_deposits.py` | CLI: categorize and report on all deposits |

## Model guidance

- **Opus** for architectural decisions, entity separation logic, legal compliance review
- **Sonnet** for extraction scripts, categorization rules, report generation
- **Haiku** for bulk OCR processing, simple file operations

## Recent decisions

- Config-driven paths (not gitignored data/ folders) -- chosen for cleaner separation
- pdfplumber preferred over tesseract for text-based PDFs (10x faster, more accurate)
- Two-phase Centier parser: collect date+desc entries and amount entries separately, then zip
- USAA multi-line parser: regex for MM/DD + debit/credit/balance columns, continuation line collection
- Deposit categorization uses keyword matching with hierarchy: crypto > payroll > business > transfer > interest > refund > generic deposit
