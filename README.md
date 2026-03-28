# Silver Shield

Financial bookkeeping armor for family law discovery, small business reporting, and personal financial organization.

Silver Shield automates bank statement extraction, transaction categorization, entity separation, and Excel ledger generation. Built for the volume and complexity of financial discovery in divorce proceedings, but useful for anyone who needs to turn a pile of bank statement PDFs into an auditable financial picture.

## What it does

- Extracts transactions from bank statement PDFs (Centier, USAA, with OCR fallback for scanned documents)
- Categorizes deposits: payroll, business income, crypto, transfers, peer payments, check deposits
- Separates transactions by legal entity (personal, business entities)
- Generates Excel ledgers with P&L, general ledger, account summary, parent debt tracking
- Tracks compliance with deficiency letter items via HTML dashboard
- Identifies potential parent/family loans by distinguishing direct deposits from check deposits

## Quick start

```bash
# Clone
git clone https://github.com/erictylerz/silver-shield.git
cd silver-shield

# Install dependencies
pip install -r requirements.txt

# Configure your paths
cp config.yaml.example config.yaml
# Edit config.yaml with your statement locations and entity mappings

# Extract transactions from all statements
python scripts/extract_all.py

# Build the Excel ledger
python scripts/build_ledger.py

# Analyze deposits
python scripts/analyze_deposits.py

# Generate deficiency tracker
python scripts/generate_tracker.py
```

## Configuration

All paths and entity mappings are defined in `config.yaml`. No personal data is stored in the repository.

```yaml
case:
  name: "Your Case Name"
  number: "2024XX00000"

data_dir: /absolute/path/to/bank/statements
output_dir: /absolute/path/to/output

entities:
  - name: "Your Name"
    type: personal
    accounts:
      - id: "x1234"
        institution: "Your Bank"
        type: "checking"
```

See `config.yaml.example` for the full configuration reference.

## Requirements

- Python 3.10+
- pdfplumber (PDF text extraction)
- openpyxl (Excel generation)
- pdftotext / poppler-utils (Centier columnar format)
- tesseract (OCR for image-based statements, optional)
- PyYAML (configuration)

## Architecture

```
silver_shield/          Core Python package
  config.py             Config loader
  extractors/           Bank statement parsers
  categorizers/         Transaction classification
  ledger/               Excel workbook builder
  compliance/           CI 42 audit framework
  reports/              Dashboard generators
scripts/                CLI entry points
templates/              Ledger and report templates
```

## Part of the ericzosso.com ecosystem

Silver Shield is a Livestock creature in the [Dominion ecosystem](https://github.com/erictylerz/stewardship-exchange). It follows the CI 42 compliance series for financial audit integrity and observes Sabbath rest (no automated runs on Sunday).

## License

MIT License. Copyright 2026 Eric Zosso.
