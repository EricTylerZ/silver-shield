"""
Silver Shield Dashboard -- Standalone financial bookkeeping interface.

Serves on port 5003. Provides a web UI for Silver Shield's tools:
statement extraction, ledger building, deposit analysis, compliance checks,
and deficiency tracking.
"""

import json
import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from flask import Flask, jsonify, render_template, request

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
DATA_DIR = PROJECT_ROOT / "data"

app = Flask(__name__, template_folder=str(APP_ROOT / "templates"))


# ---------------------------------------------------------------------------
# Core engine initialization (lazy -- only when engine endpoints are hit)
# ---------------------------------------------------------------------------

_engine = {}


def _get_engine():
    """Lazy-init the core accounting engine."""
    if not _engine:
        try:
            from silver_shield.storage.json_store import JsonStore
            from silver_shield.resources.tracker import ResourceTracker
            from silver_shield.integrations.merit import MeritBridge
            from silver_shield.integrations.auto_agent import AutoAgentBridge

            store = JsonStore(str(DATA_DIR / "engine"))
            tracker = ResourceTracker(store)
            tracker.currencies.initialize_defaults()

            from silver_shield.oracle.rates import RateSetter
            from silver_shield.integrations.reconcile import MeritReconciler

            _engine["store"] = store
            _engine["tracker"] = tracker
            _engine["merit"] = MeritBridge(tracker)
            _engine["auto_agent"] = AutoAgentBridge(tracker)
            _engine["rates"] = RateSetter(store)
            _engine["reconciler"] = MeritReconciler(tracker)
        except Exception as e:
            _engine["error"] = str(e)

    return _engine


@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin", "")
    if origin.startswith("http://localhost:"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _load_config():
    """Try to load Silver Shield config. Returns dict or None."""
    try:
        from silver_shield.config import Config
        return Config()
    except Exception:
        return None


def _load_json(path):
    """Load a JSON file, return None on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _git_info():
    """Get current git state."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True, timeout=5
        ).strip()
        log = subprocess.check_output(
            ["git", "log", "--oneline", "-5"],
            cwd=str(PROJECT_ROOT), text=True, timeout=5
        ).strip().splitlines()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT), text=True, timeout=5
        ).strip()
        return {
            "branch": branch,
            "recent_commits": log,
            "has_changes": bool(status),
            "changed_files": len(status.splitlines()) if status else 0,
        }
    except Exception:
        return {"branch": "unknown", "recent_commits": [], "has_changes": False, "changed_files": 0}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/discovery")
def discovery():
    return render_template("discovery.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    """Overall Silver Shield status."""
    config = _load_config()
    git = _git_info()

    if config:
        entities = [
            {
                "name": e.name,
                "type": e.type,
                "accounts": [
                    {"id": a.id, "institution": a.institution, "type": a.type,
                     "label": a.label, "parser": a.parser}
                    for a in e.accounts
                ],
            }
            for e in config.entities
        ]
        account_count = len(config.all_accounts())
        case_name = config.case_name
        case_number = config.case_number
        output_dir = str(config.output_dir)
        data_dir = str(config.data_dir)
    else:
        entities = []
        account_count = 0
        case_name = "Not configured"
        case_number = ""
        output_dir = ""
        data_dir = ""

    return jsonify({
        "configured": config is not None,
        "case_name": case_name,
        "case_number": case_number,
        "data_dir": data_dir,
        "output_dir": output_dir,
        "entities": entities,
        "account_count": account_count,
        "git": git,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/extraction")
def api_extraction():
    """Extraction status -- checks for all_transactions.json."""
    config = _load_config()
    if not config:
        return jsonify({"available": False, "reason": "No config.yaml"})

    txn_path = config.output_dir / "all_transactions.json"
    if not txn_path.exists():
        return jsonify({
            "available": True,
            "has_data": False,
            "message": "No extraction data yet. Run: python scripts/extract_all.py",
        })

    data = _load_json(txn_path)
    if not data:
        return jsonify({"available": True, "has_data": False, "message": "Could not read transactions file"})

    summary = data.get("summary", {})
    accounts = {}
    for acct_id, acct in data.get("accounts", {}).items():
        totals = acct.get("totals", {})
        accounts[acct_id] = {
            "label": acct.get("label", acct_id),
            "entity": acct.get("entity", ""),
            "institution": acct.get("institution", ""),
            "statements": totals.get("statements", 0),
            "deposits": totals.get("deposits", 0),
            "withdrawals": totals.get("withdrawals", 0),
            "deposit_total": totals.get("deposit_total", 0),
            "withdrawal_total": totals.get("withdrawal_total", 0),
            "mismatches": totals.get("mismatches", 0),
        }

    return jsonify({
        "available": True,
        "has_data": True,
        "summary": summary,
        "accounts": accounts,
    })


@app.route("/api/deposits")
def api_deposits():
    """Deposit analysis data."""
    config = _load_config()
    if not config:
        return jsonify({"available": False})

    analysis_path = config.output_dir / "deposit_analysis.json"
    if not analysis_path.exists():
        return jsonify({"available": True, "has_data": False,
                        "message": "Run: python scripts/analyze_deposits.py"})

    data = _load_json(analysis_path)
    return jsonify({"available": True, "has_data": True, "data": data})


@app.route("/api/compliance")
def api_compliance():
    """Run CI 42 compliance checks and return results."""
    config = _load_config()
    if not config:
        return jsonify({"available": False})

    try:
        from silver_shield.compliance.ci42 import CI42Checker
        checker = CI42Checker(config)
        results = checker.run_all()
        return jsonify({
            "available": True,
            "results": [
                {
                    "check_id": r.check_id,
                    "name": r.name,
                    "severity": r.severity,
                    "passed": r.passed,
                    "details": r.details,
                }
                for r in results
            ],
            "passed": sum(1 for r in results if r.passed),
            "total": len(results),
        })
    except Exception as e:
        return jsonify({"available": True, "error": str(e)})


@app.route("/api/deficiency")
def api_deficiency():
    """Deficiency tracker status from config."""
    config = _load_config()
    if not config:
        return jsonify({"available": False})

    items = []
    for item in config.deficiency_items:
        items.append({
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "status": item.status,
            "percent": item.percent,
        })

    complete = sum(1 for i in items if i["status"] == "complete")
    partial = sum(1 for i in items if i["status"] == "partial")
    missing = sum(1 for i in items if i["status"] == "missing")

    return jsonify({
        "available": True,
        "items": items,
        "complete": complete,
        "partial": partial,
        "missing": missing,
        "total": len(items),
    })


@app.route("/api/coverage")
def api_coverage():
    """Statement coverage per account per month — identifies gaps."""
    config = _load_config()
    if not config:
        return jsonify({"available": False})

    txn_path = config.output_dir / "all_transactions.json"
    if not txn_path.exists():
        return jsonify({"available": True, "has_data": False,
                        "message": "Run extract first"})

    data = _load_json(txn_path)
    if not data:
        return jsonify({"available": True, "has_data": False})

    def month_range(start, end):
        from datetime import datetime as dt
        s = dt.strptime(start[:7], "%Y-%m")
        e = dt.strptime(end[:7], "%Y-%m")
        while s <= e:
            yield s.strftime("%Y-%m")
            s = s.replace(year=s.year + 1, month=1) if s.month == 12 else s.replace(month=s.month + 1)

    global_min, global_max = "2099-12", "2000-01"
    accounts = {}

    for acct_id, acct_data in data.get("accounts", {}).items():
        coverage = {}
        for stmt in acct_data.get("statements", []):
            ps, pe = stmt.get("period_start", ""), stmt.get("period_end", "")
            if not ps or not pe:
                continue
            if ps[:7] < global_min: global_min = ps[:7]
            if pe[:7] > global_max: global_max = pe[:7]
            txn_count = len(stmt.get("deposits", [])) + len(stmt.get("withdrawals", []))
            for m in month_range(ps, pe):
                if m not in coverage or txn_count > coverage[m].get("txns", 0):
                    coverage[m] = {
                        "txns": txn_count,
                        "mismatches": len(stmt.get("mismatches", [])),
                        "balance": stmt.get("closing_balance", 0),
                        "file": stmt.get("file", ""),
                    }

        accounts[acct_id] = {
            "entity": acct_data.get("entity", ""),
            "institution": acct_data.get("institution", ""),
            "label": acct_data.get("label", acct_id),
            "total_stmts": len(acct_data.get("statements", [])),
            "total_txns": sum(
                len(s.get("deposits", [])) + len(s.get("withdrawals", []))
                for s in acct_data.get("statements", [])
            ),
            "coverage": coverage,
        }

    all_months = list(month_range(global_min, global_max)) if global_min < global_max else []

    return jsonify({
        "available": True,
        "has_data": True,
        "months": all_months,
        "accounts": accounts,
    })


# ---------------------------------------------------------------------------
# Core Engine API -- entity tree, accounts, ledger, resources, merit
# ---------------------------------------------------------------------------

@app.route("/api/accounts")
def api_accounts():
    """All accounts across all entities -- flat list for ecosystem sync.

    This is the endpoint EZ Merit Notify and other ecosystem projects
    call to discover wallet balances. Returns every account with its
    owning entity, currency, type, and current balance.
    """
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    tree = eng["tracker"].get_entity_tree()
    accounts = []
    for entity in tree:
        for acct in entity["accounts"]:
            accounts.append({
                "id": acct["id"],
                "name": acct["name"],
                "type": acct["type"],
                "currency": acct["currency"],
                "balance": acct["balance"],
                "active": acct["active"],
                "entity": entity["slug"],
                "entity_name": entity["name"],
                "entity_type": entity["type"],
            })

    return jsonify({"available": True, "accounts": accounts})


@app.route("/api/engine/entities")
def api_engine_entities():
    """Full entity tree with account balances."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    tree = eng["tracker"].get_entity_tree()
    return jsonify({"available": True, "entities": tree})


@app.route("/api/engine/entity/<slug>")
def api_engine_entity(slug):
    """Resource summary for a single entity."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    try:
        summary = eng["tracker"].get_entity_summary(slug)
        return jsonify({"available": True, **summary})
    except ValueError as e:
        return jsonify({"available": True, "error": str(e)}), 404


@app.route("/api/engine/accounts/<entity_slug>")
def api_engine_accounts(entity_slug):
    """Accounts + balances for an entity."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    try:
        entity = eng["tracker"].entities.get_by_slug(entity_slug)
        if entity is None:
            return jsonify({"error": f"Entity '{entity_slug}' not found"}), 404

        trial = eng["tracker"].accounts.trial_balance(entity.id)
        accounts = []
        for row in trial:
            acct = row["account"]
            accounts.append({
                "id": acct.id,
                "name": acct.name,
                "type": acct.account_type.value,
                "currency": acct.currency_code,
                "balance": str(row["balance"]),
                "active": acct.is_active,
            })

        return jsonify({"available": True, "entity": entity_slug, "accounts": accounts})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/engine/ledger/<account_id>")
def api_engine_ledger(account_id):
    """Ledger entries for a specific account."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    limit = request.args.get("limit", 50, type=int)
    entries = eng["tracker"].ledger.get_entries(account_id, limit=limit)

    return jsonify({
        "available": True,
        "account_id": account_id,
        "entries": [
            {
                "id": e.id,
                "transaction_id": e.transaction_id,
                "entry_type": e.entry_type.value,
                "amount": str(e.amount),
                "balance_after": str(e.balance_after),
                "description": e.description,
                "entry_date": e.entry_date.isoformat(),
                "source_system": e.source_system,
                "reference_id": e.reference_id,
            }
            for e in entries
        ],
    })


@app.route("/api/engine/trial-balance/<entity_slug>")
def api_engine_trial_balance(entity_slug):
    """Trial balance for an entity."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    try:
        balances = eng["tracker"].get_all_balances(entity_slug)
        return jsonify({
            "available": True,
            "entity": entity_slug,
            "rows": [
                {
                    "account": r["account"].name,
                    "type": r["account"].account_type.value,
                    "currency": r["currency_code"],
                    "balance": str(r["balance"]),
                }
                for r in balances
            ],
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/engine/currencies")
def api_engine_currencies():
    """List all registered currencies."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    currencies = eng["tracker"].currencies.list_all()
    return jsonify({
        "available": True,
        "currencies": [
            {
                "code": c.code, "name": c.name, "symbol": c.symbol,
                "precision": c.precision, "convertible": c.is_convertible,
            }
            for c in currencies
        ],
    })


# ---------------------------------------------------------------------------
# Merit Bridge API
# ---------------------------------------------------------------------------

@app.route("/api/merit/balance/<project_slug>")
def api_merit_balance(project_slug):
    """Merit balance for a project -- the ecosystem bridge endpoint."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    try:
        balance = eng["merit"].get_balance(project_slug)
        return jsonify({
            "project": project_slug,
            "balance": str(balance),
            "currency": "MERIT",
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/merit/can-afford/<project_slug>")
def api_merit_can_afford(project_slug):
    """Check if a project can afford a merit action."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    action = request.args.get("action", "")
    count = request.args.get("count", 1, type=int)

    try:
        result = eng["merit"].can_afford(project_slug, action, count)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/merit/spend", methods=["POST"])
def api_merit_spend():
    """Record merit spending for a project."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        result = eng["merit"].spend(
            project_slug=data["project"],
            action=data["action"],
            count=data.get("count", 1),
            description=data.get("description"),
            idempotency_key=data.get("idempotency_key"),
        )
        return jsonify(result)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/merit/costs")
def api_merit_costs():
    """Return the merit cost table."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})
    return jsonify(eng["merit"].get_cost_table())


@app.route("/api/merit/reconcile", methods=["POST"])
def api_merit_reconcile():
    """
    Reconcile external merit events against Silver Shield's ledger.

    Body: {"events": [
      {"action": "mint", "entity": "eric", "amount": 10000,
       "authorized_by": "eric", "source_system": "ez_merit_points",
       "source_ref": "79b8e66"},
      {"action": "allocate", "from_entity": "eric", "to_entity": "auto-agent",
       "amount": 500, "source_system": "ez_merit_points",
       "source_ref": "79b8e66-alloc-auto-agent"}
    ]}

    Silver Shield is the single ledger of record. This endpoint
    ingests external events and records them canonically.
    """
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data or "events" not in data:
        return jsonify({"error": "JSON body with 'events' list required"}), 400

    result = eng["reconciler"].reconcile_batch(data["events"])
    return jsonify(result)


@app.route("/api/merit/supply")
def api_merit_supply():
    """
    Canonical merit supply report.

    This is the authoritative answer to "how much merit exists" --
    derived from Silver Shield's double-entry ledger.
    """
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    return jsonify(eng["reconciler"].get_merit_supply())


# ---------------------------------------------------------------------------
# Resource management API (mint, allocate)
# ---------------------------------------------------------------------------

@app.route("/api/resources/mint", methods=["POST"])
def api_resources_mint():
    """Mint currency into a treasury (human authority required)."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        result = eng["tracker"].mint(
            entity_slug=data["entity"],
            amount=Decimal(str(data["amount"])),
            currency_code=data["currency"],
            description=data.get("description", "Manual mint"),
            authorized_by=data.get("authorized_by"),
            idempotency_key=data.get("idempotency_key"),
        )
        return jsonify(result)
    except (ValueError, PermissionError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/resources/allocate", methods=["POST"])
def api_resources_allocate():
    """Allocate resources from one entity to another."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        result = eng["tracker"].allocate(
            from_entity_slug=data["from"],
            to_entity_slug=data["to"],
            amount=Decimal(str(data["amount"])),
            currency_code=data["currency"],
            description=data.get("description", "Resource allocation"),
            idempotency_key=data.get("idempotency_key"),
        )
        return jsonify(result)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/resources/spend", methods=["POST"])
def api_resources_spend():
    """Record spending for an entity."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        result = eng["tracker"].record_spending(
            entity_slug=data["entity"],
            amount=Decimal(str(data["amount"])),
            currency_code=data["currency"],
            description=data.get("description", ""),
            category=data.get("category", "operating"),
            source_system=data.get("source_system", "manual"),
            idempotency_key=data.get("idempotency_key"),
        )
        return jsonify(result)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# Entity management API
# ---------------------------------------------------------------------------

@app.route("/api/rates/latest/<from_currency>/<to_currency>")
def api_rates_latest(from_currency, to_currency):
    """Get latest exchange rate for a currency pair."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    rate = eng["rates"].get_rate(from_currency, to_currency)
    if rate is None:
        return jsonify({"from": from_currency, "to": to_currency, "rate": None,
                        "message": "No rate recorded. Set via POST /api/rates/set"})
    return jsonify({"from": from_currency, "to": to_currency, "rate": str(rate)})


@app.route("/api/rates/set", methods=["POST"])
def api_rates_set():
    """Record closing prices. Body: {"closes": {"XAG": "29.50", "BTC": "67000"}, "source": "manual"}"""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data or "closes" not in data:
        return jsonify({"error": "JSON body with 'closes' dict required"}), 400

    closes = {k: Decimal(str(v)) for k, v in data["closes"].items()}
    source = data.get("source", "manual")
    results = eng["rates"].set_daily_closes(closes, source)
    return jsonify({"recorded": len(results), "source": source})


@app.route("/api/bootstrap", methods=["POST"])
def api_bootstrap():
    """
    Bootstrap entity hierarchy from ecosystem registry.

    Body: {"human_name": "Eric", "human_slug": "eric",
           "mint_merit": 10000, "per_project": 500}
    """
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        from silver_shield.integrations.ecosystem import EcosystemBootstrap

        bootstrap = EcosystemBootstrap(eng["tracker"])
        result = bootstrap.bootstrap(
            human_name=data.get("human_name", "Eric"),
            human_slug=data.get("human_slug", "eric"),
        )

        mint_result = None
        if data.get("mint_merit"):
            mint_result = bootstrap.mint_and_allocate(
                human_slug=data.get("human_slug", "eric"),
                merit_amount=Decimal(str(data["mint_merit"])),
                per_project_merit=Decimal(str(data["per_project"])) if data.get("per_project") else None,
            )

        return jsonify({
            "bootstrap": result,
            "mint": mint_result,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/engine/entity", methods=["POST"])
def api_create_entity():
    """Create a new entity in the hierarchy."""
    eng = _get_engine()
    if "error" in eng:
        return jsonify({"available": False, "error": eng["error"]})

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        from silver_shield.core.models import EntityType
        entity = eng["tracker"].entities.create(
            name=data["name"],
            slug=data["slug"],
            entity_type=EntityType(data["type"]),
            parent_id=data.get("parent_id"),
            metadata=data.get("metadata", {}),
        )
        return jsonify({
            "id": entity.id, "slug": entity.slug, "name": entity.name,
            "type": entity.entity_type.value, "parent_id": entity.parent_id,
            "human_authority": entity.human_authority,
        }), 201
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/run/<script>", methods=["POST"])
def api_run_script(script):
    """Run a Silver Shield CLI script. Returns output."""
    allowed = {
        "extract": "scripts/extract_all.py",
        "ledger": "scripts/build_ledger.py",
        "analyze": "scripts/analyze_deposits.py",
        "tracker": "scripts/generate_tracker.py",
    }
    if script not in allowed:
        return jsonify({"error": f"Unknown script: {script}"}), 400

    script_path = PROJECT_ROOT / allowed[script]
    if not script_path.exists():
        return jsonify({"error": f"Script not found: {allowed[script]}"}), 404

    try:
        result = subprocess.run(
            ["python", str(script_path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=120,
        )
        return jsonify({
            "script": script,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Script timed out (120s limit)"}), 504


def main():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5003
    print(f"Silver Shield Dashboard starting on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()
