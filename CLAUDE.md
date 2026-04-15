# Silver Shield -- Financial Bookkeeping Armor

## What is Silver Shield?

Silver Shield is financial bookkeeping armor -- it preserves and protects resources so they can ultimately be invested. Like community-shield is one tool that builds all websites, Silver Shield is one tool that manages accounting for all projects in the ecosystem.

Any entity -- person, business, project, or agent -- gets its own books. Auto-agent is the top-level agent (under the human), and each project has its own accounts. Distributist principles applied fractally: resources managed at the lowest competent level (subsidiarity), with upward reporting to the human authority at the root.

An agent unto itself is not acceptable. Every agent serves a person. Agents may manage sub-agents, each with their own accounting, but there is always a human at the top.

Silver Shield tracks resources in any unit of exchange: USD, silver (troy oz), EZ merit points, Bitcoin, Ethereum, or custom currencies. It runs **entirely offline** -- Angular frontend and Flask backend both serve from localhost only. Financial data never leaves the machine.

## Architecture

```
silver_shield/
  config.py             -- YAML config loader (currencies, hierarchy, oracle)
  core/                 -- Accounting engine (the heart)
    models.py           -- Four primitives: Entity, Account, Currency, Entry
    ledger.py           -- Append-only double-entry ledger
    double_entry.py     -- Transaction patterns (deposit, withdrawal, transfer, liability)
    entities.py         -- Hierarchy management, human-authority validation
    accounts.py         -- Account operations (open, close, balance, trial balance)
    currencies.py       -- Currency registry
  storage/              -- Persistence (offline only)
    base.py             -- Abstract interface
    json_store.py       -- JSONL file backend (local, no deps)
  oracle/               -- Exchange rate sources
  resources/            -- Per-entity resource tracking
  integrations/         -- EZ Merit, Community Shield, Auto-Agent, Stewardship Exchange
  extractors/           -- Bank statement parsers (Centier, USAA, OCR)
  categorizers/         -- Deposit classification engine
  ledger/               -- Excel workbook builder
  compliance/           -- CI 42 audit checks + deficiency tracker
  reports/              -- Report generators
dashboard/              -- Flask API + admin UI (port 5003)
frontend/               -- Angular 21 dashboard (future)
scripts/                -- CLI entry points
data/                   -- Local data (gitignored)
```

## Core Design Principles

- **Four primitives**: Entity, Account, Currency, Entry. Everything composes from these.
- **Double-entry**: Every transaction creates a debit and credit of equal amount. Single-entry cannot be audited.
- **Append-only ledger**: Entries are never modified or deleted. Corrections are new entries.
- **Idempotency**: Duplicate-safe via idempotency keys (EZ Merit pattern).
- **Human authority at root**: Entity hierarchy always terminates at a person.
- **Multi-currency**: Each account holds one currency. Cross-currency transactions create linked pairs.
- **Offline only**: Angular frontend + Flask backend serve from localhost. No cloud storage. JSON/JSONL is the production backend.
- **Config-driven**: No personal data in the repo. All paths via config.yaml.
- **One tool, all projects**: Like community-shield builds all websites, Silver Shield manages accounting for all projects. Auto-agent is the top agent entity, each project gets its own accounts.

## Modules

### Bank Statement Pipeline (existing)
Parses PDFs, categorizes deposits, builds Excel ledgers. This is one tool within Silver Shield, not its identity.

### Core Accounting Engine
The four primitives + append-only double-entry ledger. Storage-agnostic (JSON locally, Supabase for production).

### Exchange Rate Oracle
Silver spot (via community-shield), crypto prices (CoinGecko), merit points (not convertible -- site-sovereign per Stewardship Exchange spec).

### Resource Tracking
Per-entity budgets, token usage, API costs. Enables tracking which project is doing well.

### Integrations
- **EZ Merit**: Read balances, award points for financial milestones
- **Community Shield**: Silver spot price, agent registration, Supabase
- **Auto-Agent**: Token budget sync, resource consumption recording
- **Stewardship Exchange**: Enrollment balance display (read-only)

## Rules and constraints

- **Never commit PII.** No account numbers, names, balances, or transaction data in the repo.
- **Blue/Black/Green convention.** Blue text = hardcoded inputs. Black = formulas/data. Green = cross-sheet links. Yellow background = needs attention.
- **Zero formula errors.** Every Excel output must pass recalc verification with 0 errors.
- **Subsidiarity.** Automate extraction and categorization. Human reviews before legal assertion.
- **Sabbath.** No automated batch runs on Sunday.
- **Double-entry integrity.** Every transaction must create balanced debit/credit entries.
- **Append-only.** Ledger entries are never modified or deleted.

## Data safety -- NEVER read financial data

Claude Code must NEVER read files containing actual financial data. All financial data stays local; the dashboard and scripts process it at runtime on localhost.

**Never read:**
- `config.yaml` (use `config.yaml.example` for reference)
- Anything in `data/` or the configured `output_dir`
- Any `.pdf`, `.xlsx`, or extracted `.json` transaction files
- Any file path outside this repo that might contain user financial data

**Always safe to read:**
- All `.py` source files in `silver_shield/`, `scripts/`, `dashboard/`, `tests/`
- `config.yaml.example`, `.dominion.json`, `.dashboard.json`
- Templates, HTML, CSS, requirements.txt, .gitignore

**When debugging:** The user will describe errors and paste relevant output. Do not read output files to diagnose -- ask the user what they see.

A `PreToolUse` hook in `.claude/settings.local.json` enforces this automatically.

## Key files

| File | Purpose |
|------|---------|
| `silver_shield/core/models.py` | Four primitives: Entity, Account, Currency, Entry |
| `silver_shield/core/ledger.py` | Append-only double-entry ledger engine |
| `silver_shield/core/double_entry.py` | Transaction patterns (deposit, withdrawal, transfer) |
| `silver_shield/core/entities.py` | Entity hierarchy, human-authority validation |
| `silver_shield/core/accounts.py` | Account operations |
| `silver_shield/storage/json_store.py` | JSONL file persistence |
| `silver_shield/config.py` | YAML config loader |
| `silver_shield/extractors/centier.py` | Centier bank statement parser |
| `silver_shield/extractors/usaa.py` | USAA statement parser |
| `silver_shield/categorizers/deposits.py` | Deposit classification engine |
| `silver_shield/ledger/builder.py` | Excel workbook generator |
| `silver_shield/compliance/ci42.py` | CI 42 compliance checks |
| `silver_shield/compliance/deficiency.py` | Deficiency tracker |
| `dashboard/app.py` | Flask API + dashboard (port 5003) |
| `tests/test_core.py` | Core engine tests (36 tests) |

## Model guidance

- **Opus** for architectural decisions, entity hierarchy design, compliance review
- **Sonnet** for extraction scripts, categorization rules, API endpoints
- **Haiku** for bulk OCR processing, simple file operations

## Resource Governance (Effective 2026-04-14)
Per Commander's Directive (compliance-inspector/COMMANDER_DIRECTIVE.md):
- **80% Context Rule:** After 80% context usage, no parallel Agent calls — sequential only.
- **Quadratic Merit Priority:** priority = sqrt(merit_balance). Silver Shield is ledger of record.
- Read the full directive before doing work.
