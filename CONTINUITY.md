# Silver Shield -- Continuity Binder

## Current State (2026-04-02)

### Architecture
Silver Shield is the ecosystem's financial steward. Fractal accounting: every entity gets its own books. Four primitives (Entity, Account, Currency, Entry) compose into a double-entry ledger that's append-only and idempotent. Multi-currency: USD, XAG (silver), MERIT, BTC, ETH. Everything offline -- Angular 21 frontend + Flask backend on localhost.

Two layers:
1. **Core accounting engine** -- entity hierarchy, ledger, double-entry transactions, resource tracking, merit bridge
2. **Bank statement pipeline** -- PDF extraction, categorization, Excel ledger builder, compliance checks

### What's Built and Working

**Core Engine (Phase 1 + 2 complete)**
- `core/models.py` -- Entity, Account, Currency, Entry with enum types, normal balance rules
- `core/ledger.py` -- Append-only double-entry with idempotency
- `core/double_entry.py` -- Deposit, withdrawal, transfer, liability patterns
- `core/entities.py` -- Hierarchy management, human-authority constraint enforcement
- `core/accounts.py` -- Open, close, balance, trial balance
- `core/currencies.py` -- Currency registry with defaults
- `storage/json_store.py` -- JSONL file backend, thread-safe, complete serialization

**Resource Tracking (Phase 2 -- built 2026-04-02)**
- `resources/tracker.py` -- Wraps core engine. Mint, allocate, spend, balance queries, entity tree, ledger access
- `integrations/merit.py` -- EZ Merit ledger bridge. Cost table per CI 40-703.7. can_afford() + spend() with double-entry
- `integrations/auto_agent.py` -- Token usage recording, budget checks (CI 90-001.3), project funding

**Dashboard (Flask, port 5003)**
- 9 original endpoints: status, extraction, deposits, compliance, deficiency, coverage, run script
- 15 new engine endpoints: entity CRUD, accounts, ledger entries, trial balance, currencies, merit balance/spend/costs, resource mint/allocate/spend
- CORS for Angular frontend at :4200
- Registered in community-shield at :4222, .dashboard.json created

**Angular 21 Frontend**
- 9 routes: dashboard, entities, accounts/:slug, ledger/:accountId, compliance, deficiency, resources, discovery, feedback
- Entity tree with expand/collapse and account chips
- Account detail with currency summaries
- Ledger browser with pagination
- Compliance view (CI 42 results, pass rate)
- Deficiency tracker (progress bars, status)
- Resources view (merit costs, currencies, entity balances)

**Bank Statement Pipeline**
- Centier parser (columnar), USAA parser (multi-line), OCR fallback
- Deposit categorization with keyword hierarchy
- Excel ledger builder (7-sheet workbook, color conventions)
- CI 42 compliance checker (5 checks), deficiency tracker

**Tests**
- 62 tests passing (models, entities, ledger, double-entry, multi-currency, persistence, resource tracker, merit bridge, auto-agent bridge)

### What's NOT Built Yet
- Entity hierarchy is empty in the engine -- no entities bootstrapped yet
- Exchange rates -- just need previous day close prices, nothing real-time
- Reports module (empty stub)
- Import wizard in Angular frontend (bank statement -> ledger flow)

### The Actual Bottleneck
The resource tracking code and API are live, but:
1. Nobody has created entities in the core engine (the tree is empty)
2. No merit has been minted into any treasury
3. No allocations have been made to project accounts
4. EZ Merit Notify still reads from its own wallets.json instead of calling Silver Shield's API

The bridge exists. The roads to it haven't been paved yet.

### Cross-Project Integration Points
- **EZ Merit Notify** -- Should call `/api/merit/balance/<project>` instead of reading wallets.json. Should call `/api/merit/spend` when sending emails.
- **Auto-Agent** -- Should call `/api/resources/spend` for token usage. Should call `/api/merit/can-afford` before sending briefs.
- **Compliance Inspector** -- Subordinate policy in `.dominion.json`. CI 42 series.
- **Community Shield** -- `.dashboard.json` provides widgets for :4222 project page.

### Architectural Decisions
1. Config-driven, not data-in-repo. All paths via config.yaml.
2. pdfplumber over tesseract for text PDFs.
3. Exchange rates: previous day close prices only. No real-time feeds.
4. Merit balances computed from double-entry ledger, never stored separately.
5. Entity hierarchy always terminates at a human. Agents serve people.
6. JSONL append-only for ledger entries. JSON arrays for entities/accounts/currencies.

### Next Session Priority
1. Bootstrap entity hierarchy (root person + projects)
2. Mint initial merit into treasury, allocate to projects
3. Wire EZ Merit Notify to read from Silver Shield instead of wallets.json
4. Simple rate setter for previous-day close prices
5. Import wizard in Angular frontend
