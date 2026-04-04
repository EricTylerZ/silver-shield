"""
Tests for Silver Shield core accounting engine.

Covers: models, ledger, double-entry, entities, currencies, storage.
"""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from silver_shield.core.models import (
    Entity, Account, Currency, Entry, EntryType,
    EntityType, AccountType, RateSource, CURRENCIES,
)
from silver_shield.core.ledger import Ledger
from silver_shield.core.double_entry import DoubleEntry
from silver_shield.core.entities import EntityManager
from silver_shield.core.accounts import AccountManager
from silver_shield.core.currencies import CurrencyRegistry
from silver_shield.core.models import Authorization
from silver_shield.resources.tracker import ResourceTracker
from silver_shield.resources.assets import AssetTracker, AssetCategory
from silver_shield.integrations.merit import MeritBridge
from silver_shield.integrations.auto_agent import AutoAgentBridge
from silver_shield.integrations.reconcile import MeritReconciler
from silver_shield.storage.json_store import JsonStore


@pytest.fixture
def store(tmp_path):
    return JsonStore(str(tmp_path / "data"))


@pytest.fixture
def ledger(store):
    return Ledger(store)


@pytest.fixture
def entities(store):
    return EntityManager(store)


@pytest.fixture
def accounts(store):
    return AccountManager(store)


@pytest.fixture
def currencies(store):
    return CurrencyRegistry(store)


@pytest.fixture
def double_entry(ledger, accounts):
    return DoubleEntry(ledger, accounts)


# -----------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------

class TestModels:

    def test_entry_amount_must_be_non_negative(self):
        with pytest.raises(ValueError, match="non-negative"):
            Entry(amount=Decimal("-10"))

    def test_entry_coerces_string_amount(self):
        e = Entry(amount="123.45")
        assert e.amount == Decimal("123.45")

    def test_entry_coerces_string_date(self):
        e = Entry(entry_date="2026-03-28")
        assert e.entry_date == date(2026, 3, 28)

    def test_account_normal_balance_asset(self):
        a = Account(account_type=AccountType.ASSET)
        assert a.normal_balance == EntryType.DEBIT

    def test_account_normal_balance_liability(self):
        a = Account(account_type=AccountType.LIABILITY)
        assert a.normal_balance == EntryType.CREDIT

    def test_account_normal_balance_income(self):
        a = Account(account_type=AccountType.INCOME)
        assert a.normal_balance == EntryType.CREDIT

    def test_account_normal_balance_expense(self):
        a = Account(account_type=AccountType.EXPENSE)
        assert a.normal_balance == EntryType.DEBIT

    def test_currency_format_usd(self):
        usd = CURRENCIES["USD"]
        assert usd.format(Decimal("1234.5")) == "$1,234.50"

    def test_currency_format_btc(self):
        btc = CURRENCIES["BTC"]
        assert "BTC" in btc.format(Decimal("0.00123456"))

    def test_default_currencies_exist(self):
        assert "USD" in CURRENCIES
        assert "XAG" in CURRENCIES
        assert "MERIT" in CURRENCIES
        assert "BTC" in CURRENCIES
        assert "ETH" in CURRENCIES

    def test_merit_not_convertible(self):
        assert CURRENCIES["MERIT"].is_convertible is False
        assert CURRENCIES["MERIT"].rate_source == RateSource.NONE


# -----------------------------------------------------------------------
# Entity Hierarchy
# -----------------------------------------------------------------------

class TestEntityHierarchy:

    def test_create_root_human(self, entities):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        assert root.is_root()
        assert root.is_human()
        assert root.human_authority == root.id

    def test_create_child_entity(self, entities):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        biz = entities.create("Zoseco", "zoseco", EntityType.BUSINESS,
                              parent_id=root.id)
        assert biz.parent_id == root.id
        assert biz.human_authority == root.id

    def test_create_agent_under_project(self, entities):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        project = entities.create("Silver Shield", "silver-shield",
                                  EntityType.PROJECT, parent_id=root.id)
        agent = entities.create("Agent Alpha", "agent-alpha",
                                EntityType.AGENT, parent_id=project.id)
        assert agent.human_authority == root.id

    def test_non_person_without_parent_fails(self, entities):
        with pytest.raises(ValueError, match="must have a parent"):
            entities.create("Orphan Agent", "orphan", EntityType.AGENT)

    def test_get_children(self, entities):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        biz = entities.create("Zoseco", "zoseco", EntityType.BUSINESS,
                              parent_id=root.id)
        proj = entities.create("SS", "ss", EntityType.PROJECT,
                               parent_id=root.id)
        children = entities.get_children(root.id)
        assert len(children) == 2

    def test_get_subtree(self, entities):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        biz = entities.create("Zoseco", "zoseco", EntityType.BUSINESS,
                              parent_id=root.id)
        proj = entities.create("SS", "ss", EntityType.PROJECT,
                               parent_id=biz.id)
        agent = entities.create("Bot", "bot", EntityType.AGENT,
                                parent_id=proj.id)
        subtree = entities.get_subtree(root.id)
        assert len(subtree) == 3  # biz, proj, agent

    def test_validate_human_authority(self, entities):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        agent = entities.create("Bot", "bot", EntityType.AGENT,
                                parent_id=root.id)
        assert entities.validate_human_authority(agent.id)

    def test_get_by_slug(self, entities):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        found = entities.get_by_slug("eric")
        assert found is not None
        assert found.id == root.id


# -----------------------------------------------------------------------
# Ledger (Double-Entry)
# -----------------------------------------------------------------------

class TestLedger:

    def _setup_accounts(self, store, entities, accounts):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        checking = accounts.open(root.id, "USD", AccountType.ASSET, "Checking")
        income = accounts.open(root.id, "USD", AccountType.INCOME, "Payroll")
        expense = accounts.open(root.id, "USD", AccountType.EXPENSE, "Operating")
        return root, checking, income, expense

    def test_record_transaction_creates_two_entries(
        self, store, ledger, entities, accounts
    ):
        _, checking, income, _ = self._setup_accounts(
            store, entities, accounts
        )
        debit, credit = ledger.record_transaction(
            debit_account_id=checking.id,
            credit_account_id=income.id,
            amount=Decimal("1000.00"),
            description="Payroll deposit",
        )
        assert debit.entry_type == EntryType.DEBIT
        assert credit.entry_type == EntryType.CREDIT
        assert debit.amount == credit.amount == Decimal("1000.00")
        assert debit.transaction_id == credit.transaction_id

    def test_balance_after_deposit(self, store, ledger, entities, accounts):
        _, checking, income, _ = self._setup_accounts(
            store, entities, accounts
        )
        ledger.record_transaction(
            checking.id, income.id, Decimal("500"), "Deposit"
        )
        assert ledger.get_balance(checking.id) == Decimal("500")
        assert ledger.get_balance(income.id) == Decimal("500")

    def test_multiple_transactions_accumulate(
        self, store, ledger, entities, accounts
    ):
        _, checking, income, expense = self._setup_accounts(
            store, entities, accounts
        )
        ledger.record_transaction(
            checking.id, income.id, Decimal("1000"), "Payroll"
        )
        ledger.record_transaction(
            expense.id, checking.id, Decimal("200"), "Rent"
        )
        assert ledger.get_balance(checking.id) == Decimal("800")
        assert ledger.get_balance(income.id) == Decimal("1000")
        assert ledger.get_balance(expense.id) == Decimal("200")

    def test_idempotency_prevents_duplicate(
        self, store, ledger, entities, accounts
    ):
        _, checking, income, _ = self._setup_accounts(
            store, entities, accounts
        )
        d1, c1 = ledger.record_transaction(
            checking.id, income.id, Decimal("500"), "Payroll",
            idempotency_key="payroll-001",
        )
        d2, c2 = ledger.record_transaction(
            checking.id, income.id, Decimal("500"), "Payroll",
            idempotency_key="payroll-001",
        )
        assert d1.id == d2.id
        assert c1.id == c2.id
        assert ledger.get_balance(checking.id) == Decimal("500")

    def test_zero_amount_rejected(self, store, ledger, entities, accounts):
        _, checking, income, _ = self._setup_accounts(
            store, entities, accounts
        )
        with pytest.raises(ValueError, match="positive"):
            ledger.record_transaction(
                checking.id, income.id, Decimal("0"), "Nothing"
            )

    def test_nonexistent_account_rejected(self, store, ledger, entities, accounts):
        _, checking, _, _ = self._setup_accounts(store, entities, accounts)
        with pytest.raises(ValueError, match="not found"):
            ledger.record_transaction(
                checking.id, "fake-id", Decimal("100"), "Bad"
            )

    def test_get_transaction_returns_both_entries(
        self, store, ledger, entities, accounts
    ):
        _, checking, income, _ = self._setup_accounts(
            store, entities, accounts
        )
        debit, credit = ledger.record_transaction(
            checking.id, income.id, Decimal("100"), "Test"
        )
        entries = ledger.get_transaction(debit.transaction_id)
        assert len(entries) == 2


# -----------------------------------------------------------------------
# Multi-Currency
# -----------------------------------------------------------------------

class TestMultiCurrency:

    def test_accounts_in_different_currencies(
        self, store, entities, accounts, ledger
    ):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        usd_acct = accounts.open(root.id, "USD", AccountType.ASSET, "USD Checking")
        btc_acct = accounts.open(root.id, "BTC", AccountType.ASSET, "BTC Wallet")
        usd_income = accounts.open(root.id, "USD", AccountType.INCOME, "USD Income")
        btc_income = accounts.open(root.id, "BTC", AccountType.INCOME, "BTC Income")

        ledger.record_transaction(
            usd_acct.id, usd_income.id, Decimal("5000"), "Payroll"
        )
        ledger.record_transaction(
            btc_acct.id, btc_income.id, Decimal("0.05"), "BTC received"
        )

        assert ledger.get_balance(usd_acct.id) == Decimal("5000")
        assert ledger.get_balance(btc_acct.id) == Decimal("0.05")

    def test_currency_registry_defaults(self, currencies):
        currencies.initialize_defaults()
        all_c = currencies.list_all()
        codes = {c.code for c in all_c}
        assert {"USD", "XAG", "MERIT", "BTC", "ETH"} <= codes

    def test_register_custom_currency(self, currencies):
        custom = Currency("DOGE", "Dogecoin", "DOGE", 8, True,
                          RateSource.CRYPTO_ORACLE)
        currencies.register(custom)
        found = currencies.get("DOGE")
        assert found is not None
        assert found.name == "Dogecoin"


# -----------------------------------------------------------------------
# Double-Entry Helpers
# -----------------------------------------------------------------------

class TestDoubleEntryHelpers:

    def test_transfer_between_accounts(
        self, store, entities, accounts, double_entry, ledger
    ):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        acct_a = accounts.open(root.id, "USD", AccountType.ASSET, "Checking")
        acct_b = accounts.open(root.id, "USD", AccountType.ASSET, "Savings")
        income = accounts.open(root.id, "USD", AccountType.INCOME, "Income")

        # Seed checking with 1000
        ledger.record_transaction(
            acct_a.id, income.id, Decimal("1000"), "Payroll"
        )

        # Transfer 300 from checking to savings
        double_entry.transfer(
            from_account_id=acct_a.id,
            to_account_id=acct_b.id,
            amount=Decimal("300"),
            description="Monthly savings",
        )

        assert ledger.get_balance(acct_a.id) == Decimal("700")
        assert ledger.get_balance(acct_b.id) == Decimal("300")

    def test_record_liability(
        self, store, entities, accounts, double_entry, ledger
    ):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        checking = accounts.open(root.id, "USD", AccountType.ASSET, "Checking")
        parent_loan = accounts.open(root.id, "USD", AccountType.LIABILITY,
                                     "Parent Loans")

        double_entry.record_liability(
            asset_account_id=checking.id,
            liability_account_id=parent_loan.id,
            amount=Decimal("2500"),
            description="Check deposit from family",
        )

        assert ledger.get_balance(checking.id) == Decimal("2500")
        assert ledger.get_balance(parent_loan.id) == Decimal("2500")


# -----------------------------------------------------------------------
# Storage Persistence
# -----------------------------------------------------------------------

class TestJsonStorePersistence:

    def test_entries_survive_reload(self, tmp_path):
        data_dir = str(tmp_path / "data")

        # Session 1: create and write
        store1 = JsonStore(data_dir)
        em1 = EntityManager(store1)
        am1 = AccountManager(store1)
        l1 = Ledger(store1)

        root = em1.create("Eric", "eric", EntityType.PERSON)
        checking = am1.open(root.id, "USD", AccountType.ASSET, "Checking")
        income = am1.open(root.id, "USD", AccountType.INCOME, "Income")
        l1.record_transaction(checking.id, income.id, Decimal("1000"), "Pay")

        # Session 2: reload from same files
        store2 = JsonStore(data_dir)
        l2 = Ledger(store2)
        assert l2.get_balance(checking.id) == Decimal("1000")

    def test_entity_persistence(self, tmp_path):
        data_dir = str(tmp_path / "data")

        store1 = JsonStore(data_dir)
        em1 = EntityManager(store1)
        root = em1.create("Eric", "eric", EntityType.PERSON)

        store2 = JsonStore(data_dir)
        em2 = EntityManager(store2)
        found = em2.get_by_slug("eric")
        assert found is not None
        assert found.id == root.id


# -----------------------------------------------------------------------
# Account Operations
# -----------------------------------------------------------------------

class TestAccountOperations:

    def test_close_zero_balance(self, store, entities, accounts):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        acct = accounts.open(root.id, "USD", AccountType.ASSET, "Old Account")
        closed = accounts.close(acct.id)
        assert closed.is_active is False

    def test_close_nonzero_balance_fails(
        self, store, entities, accounts, ledger
    ):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        checking = accounts.open(root.id, "USD", AccountType.ASSET, "Checking")
        income = accounts.open(root.id, "USD", AccountType.INCOME, "Income")
        ledger.record_transaction(
            checking.id, income.id, Decimal("100"), "Deposit"
        )
        with pytest.raises(ValueError, match="non-zero balance"):
            accounts.close(checking.id)

    def test_trial_balance(self, store, entities, accounts, ledger):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        checking = accounts.open(root.id, "USD", AccountType.ASSET, "Checking")
        income = accounts.open(root.id, "USD", AccountType.INCOME, "Income")
        ledger.record_transaction(
            checking.id, income.id, Decimal("500"), "Pay"
        )
        tb = accounts.trial_balance(root.id)
        assert len(tb) == 2
        balances = {r["account"].name: r["balance"] for r in tb}
        assert balances["Checking"] == Decimal("500")
        assert balances["Income"] == Decimal("500")


# -----------------------------------------------------------------------
# Resource Tracker
# -----------------------------------------------------------------------

class TestResourceTracker:

    @pytest.fixture
    def tracker(self, store, entities):
        t = ResourceTracker(store)
        t.currencies.initialize_defaults()
        # Create root human + a project
        root = entities.create("Eric", "eric", EntityType.PERSON)
        entities.create("Auto-Agent", "auto-agent", EntityType.AGENT,
                        parent_id=root.id)
        entities.create("Silver Shield", "silver-shield", EntityType.PROJECT,
                        parent_id=root.id)
        return t

    def test_mint_creates_treasury(self, tracker):
        result = tracker.mint("eric", Decimal("10000"), "MERIT",
                              "Initial treasury mint", authorized_by="eric")
        assert result["balance_after"] == "10000"
        assert result["currency"] == "MERIT"

    def test_mint_requires_human_authority(self, tracker):
        # Agent can be minted *to* as long as chain is valid
        result = tracker.mint("auto-agent", Decimal("100"), "MERIT",
                              "Agent treasury", authorized_by="eric")
        assert result["balance_after"] == "100"

    def test_allocate_transfers_between_entities(self, tracker):
        # Mint to eric, then allocate to auto-agent
        tracker.mint("eric", Decimal("5000"), "MERIT", "Mint")
        result = tracker.allocate("eric", "auto-agent", Decimal("500"),
                                  "MERIT", "Budget allocation")
        assert result["to_balance_after"] == "500"
        assert result["from_balance_after"] == "4500"

    def test_record_spending(self, tracker):
        tracker.mint("auto-agent", Decimal("200"), "MERIT",
                     "Budget", authorized_by="eric")
        result = tracker.record_spending("auto-agent", Decimal("22"),
                                         "MERIT", "Email send",
                                         category="merit_email_send",
                                         source_system="ez_merit")
        assert result["balance_after"] == "178"

    def test_spending_insufficient_funds_still_records(self, tracker):
        # With no funds, the balance goes negative (ledger allows it,
        # it's the integration layer that enforces affordability)
        tracker.mint("auto-agent", Decimal("10"), "MERIT",
                     "Small budget", authorized_by="eric")
        result = tracker.record_spending("auto-agent", Decimal("50"),
                                         "MERIT", "Overspend")
        assert result["balance_after"] == "-40"

    def test_get_balance(self, tracker):
        tracker.mint("eric", Decimal("1000"), "USD", "Capital")
        bal = tracker.get_balance("eric", "USD")
        assert bal == Decimal("1000")

    def test_get_balance_no_account(self, tracker):
        bal = tracker.get_balance("eric", "BTC")
        assert bal == Decimal("0")

    def test_get_entity_summary(self, tracker):
        tracker.mint("eric", Decimal("5000"), "USD", "Capital")
        tracker.mint("eric", Decimal("1000"), "MERIT", "Merit mint")
        summary = tracker.get_entity_summary("eric")
        assert summary["entity"] == "eric"
        assert "USD" in summary["balances"]
        assert "MERIT" in summary["balances"]

    def test_get_entity_tree(self, tracker):
        tree = tracker.get_entity_tree()
        slugs = {e["slug"] for e in tree}
        assert "eric" in slugs
        assert "auto-agent" in slugs
        assert "silver-shield" in slugs

    def test_get_entries(self, tracker):
        tracker.mint("eric", Decimal("500"), "USD", "Seed")
        entries = tracker.get_entries("eric", "USD")
        assert len(entries) > 0
        assert entries[0]["currency"] == "USD"

    def test_nonexistent_entity_raises(self, tracker):
        with pytest.raises(ValueError, match="not found"):
            tracker.get_balance("nobody", "USD")

    def test_idempotent_mint(self, tracker):
        r1 = tracker.mint("eric", Decimal("100"), "USD", "Mint",
                          idempotency_key="mint-001")
        r2 = tracker.mint("eric", Decimal("100"), "USD", "Mint",
                          idempotency_key="mint-001")
        assert r1["transaction_id"] == r2["transaction_id"]
        assert tracker.get_balance("eric", "USD") == Decimal("100")


# -----------------------------------------------------------------------
# Merit Bridge
# -----------------------------------------------------------------------

class TestMeritBridge:

    @pytest.fixture
    def merit(self, store, entities):
        t = ResourceTracker(store)
        t.currencies.initialize_defaults()
        root = entities.create("Eric", "eric", EntityType.PERSON)
        entities.create("Auto-Agent", "auto-agent", EntityType.AGENT,
                        parent_id=root.id)
        # Fund auto-agent with merit
        t.mint("eric", Decimal("10000"), "MERIT", "Treasury mint",
               authorized_by="eric")
        t.allocate("eric", "auto-agent", Decimal("500"), "MERIT",
                   "Budget allocation")
        return MeritBridge(t)

    def test_get_balance(self, merit):
        bal = merit.get_balance("auto-agent")
        assert bal == Decimal("500")

    def test_can_afford_yes(self, merit):
        check = merit.can_afford("auto-agent", "email_send", 10)
        assert check["affordable"] is True
        assert check["total_cost"] == "220"

    def test_can_afford_no(self, merit):
        check = merit.can_afford("auto-agent", "email_send", 100)
        assert check["affordable"] is False

    def test_spend(self, merit):
        result = merit.spend("auto-agent", "email_send", 2,
                             description="Sent briefs to siblings")
        assert result["amount"] == "44"
        assert result["balance_after"] == "456"

    def test_spend_insufficient(self, merit):
        with pytest.raises(ValueError, match="Insufficient merit"):
            merit.spend("auto-agent", "email_send", 100)

    def test_unknown_action_raises(self, merit):
        with pytest.raises(ValueError, match="Unknown merit action"):
            merit.spend("auto-agent", "teleport", 1)

    def test_cost_table(self, merit):
        costs = merit.get_cost_table()
        assert costs["email_send"] == "22"
        assert costs["announcement"] == "2"

    def test_mint_to_treasury(self, merit):
        result = merit.mint_to_treasury("eric", Decimal("5000"),
                                        "eric", "Additional mint")
        # eric already had 10000 - 500 = 9500, now + 5000 = 14500
        assert result["balance_after"] == "14500"

    def test_allocate_to_project(self, merit):
        result = merit.allocate_to_project("eric", "auto-agent",
                                           Decimal("100"), "Extra budget")
        # auto-agent had 500, now 600
        assert result["to_balance_after"] == "600"


# -----------------------------------------------------------------------
# Auto-Agent Bridge
# -----------------------------------------------------------------------

class TestAutoAgentBridge:

    @pytest.fixture
    def bridge(self, store, entities):
        t = ResourceTracker(store)
        t.currencies.initialize_defaults()
        root = entities.create("Eric", "eric", EntityType.PERSON)
        proj = entities.create("Auto-Agent", "auto-agent", EntityType.AGENT,
                               parent_id=root.id)
        t.mint("auto-agent", Decimal("100"), "USD",
               "API budget", authorized_by="eric")
        return AutoAgentBridge(t)

    def test_record_token_usage(self, bridge):
        result = bridge.record_token_usage(
            "auto-agent", tokens=50000,
            cost_usd=Decimal("0.15"), model="sonnet",
        )
        assert result["amount"] == "0.15"
        assert result["balance_after"] == "99.85"

    def test_check_budget_affordable(self, bridge):
        check = bridge.check_budget("auto-agent", "USD", Decimal("50"))
        assert check["affordable"] is True
        assert check["current_balance"] == "100"

    def test_check_budget_too_expensive(self, bridge):
        check = bridge.check_budget("auto-agent", "USD", Decimal("200"))
        assert check["affordable"] is False

    def test_get_resource_summary(self, bridge):
        bridge.record_token_usage("auto-agent", 10000, Decimal("0.03"), "haiku")
        summary = bridge.get_resource_summary("auto-agent")
        assert summary["entity"] == "auto-agent"
        assert len(summary["recent_entries"]) > 0

    def test_fund_project(self, bridge):
        # First mint more to eric (need to go through the tracker)
        bridge.tracker.mint("eric", Decimal("1000"), "USD",
                            "Funding", authorized_by="eric")
        result = bridge.fund_project("eric", "auto-agent",
                                     Decimal("50"), "USD", "Extra budget")
        assert result["to_balance_after"] == "150"


# -----------------------------------------------------------------------
# Ledger Corrections
# -----------------------------------------------------------------------

class TestLedgerCorrections:

    def _setup(self, store, entities, accounts):
        root = entities.create("Eric", "eric", EntityType.PERSON)
        checking = accounts.open(root.id, "USD", AccountType.ASSET, "Checking")
        income = accounts.open(root.id, "USD", AccountType.INCOME, "Income")
        return root, checking, income

    def test_correction_reverses_transaction(
        self, store, ledger, entities, accounts
    ):
        _, checking, income = self._setup(store, entities, accounts)
        debit, credit = ledger.record_transaction(
            checking.id, income.id, Decimal("500"), "Bad deposit"
        )
        auth = Authorization(
            authorized_by="eric",
            statement="Reverse unauthorized deposit per review",
            reference="CI-2026-04-04-001",
        )
        corr_d, corr_c = ledger.record_correction(
            original_transaction_id=debit.transaction_id,
            reason="Deposit was unauthorized",
            authorization=auth,
        )
        # Balances should net to zero
        assert ledger.get_balance(checking.id) == Decimal("0")
        assert ledger.get_balance(income.id) == Decimal("0")
        # Correction entries reference the original
        assert corr_d.reference_id == debit.transaction_id
        assert corr_d.authorization is not None
        assert corr_d.authorization.authorized_by == "eric"

    def test_correction_idempotency(self, store, ledger, entities, accounts):
        _, checking, income = self._setup(store, entities, accounts)
        debit, _ = ledger.record_transaction(
            checking.id, income.id, Decimal("200"), "Test"
        )
        auth = Authorization(
            authorized_by="eric", statement="Fix it", reference="ref-1",
        )
        c1_d, c1_c = ledger.record_correction(
            debit.transaction_id, "dup test", auth,
            idempotency_key="corr-001",
        )
        c2_d, c2_c = ledger.record_correction(
            debit.transaction_id, "dup test", auth,
            idempotency_key="corr-001",
        )
        assert c1_d.id == c2_d.id
        assert ledger.get_balance(checking.id) == Decimal("0")

    def test_correction_bad_transaction_raises(self, store, ledger, entities, accounts):
        self._setup(store, entities, accounts)
        auth = Authorization(
            authorized_by="eric", statement="test", reference="ref",
        )
        with pytest.raises(ValueError, match="not found or malformed"):
            ledger.record_correction("fake-txn-id", "no such txn", auth)


# -----------------------------------------------------------------------
# Resource Tracker Corrections
# -----------------------------------------------------------------------

class TestTrackerCorrections:

    @pytest.fixture
    def tracker(self, store, entities):
        t = ResourceTracker(store)
        t.currencies.initialize_defaults()
        root = entities.create("Eric", "eric", EntityType.PERSON)
        entities.create("Auto-Agent", "auto-agent", EntityType.AGENT,
                        parent_id=root.id)
        # Mint and allocate WITHOUT authorization (the unauthorized case)
        t.mint("eric", Decimal("5000"), "MERIT", "Mint", authorized_by="eric")
        t.allocate("eric", "auto-agent", Decimal("500"), "MERIT",
                   "Unauthorized allocation")
        return t

    def test_find_unauthorized_allocations(self, tracker):
        unauth = tracker.find_unauthorized_allocations("eric")
        assert len(unauth) > 0
        assert unauth[0]["amount"] == "500"

    def test_correct_allocation_reverses_and_authorizes(self, tracker):
        unauth = tracker.find_unauthorized_allocations("eric")
        txn_id = unauth[0]["transaction_id"]

        auth = Authorization(
            authorized_by="eric",
            statement="Reverse the 500 MERIT allocation that lacked authorization",
            reference="CI-2026-04-04-002",
        )
        result = tracker.correct_allocation(txn_id, "No authorization", auth)
        assert result["original_transaction_id"] == txn_id
        assert result["amount"] == "500"
        assert result["authorized_by"] == "eric"

        # auto-agent balance should be back to 0
        bal = tracker.get_balance("auto-agent", "MERIT")
        assert bal == Decimal("0")


# -----------------------------------------------------------------------
# Physical Asset Tracker
# -----------------------------------------------------------------------

class TestAssetTracker:

    @pytest.fixture
    def asset_tracker(self, store, entities):
        at = AssetTracker(store)
        root = entities.create("Eric", "eric", EntityType.PERSON)
        # Give eric a USD asset account so he can pay for things
        accts = AccountManager(store)
        accts.open(root.id, "USD", AccountType.ASSET, "USD Checking")
        # Seed with funds
        ledger = Ledger(store)
        equity = accts.open(root.id, "USD", AccountType.EQUITY, "Equity")
        ledger.record_transaction(
            accts.list_for_entity(root.id)[0].id,
            equity.id,
            Decimal("50000"), "Seed capital",
        )
        return at

    def test_register_asset_creates_entity_and_accounts(self, asset_tracker):
        result = asset_tracker.register_asset(
            owner_slug="eric",
            name="2006 Toyota Camry",
            slug="camry",
            category=AssetCategory.VEHICLE,
            original_value=Decimal("4500"),
        )
        assert result["slug"] == "camry"
        assert result["category"] == "vehicle"
        assert result["book_value"] == "4500"

    def test_record_depreciation(self, asset_tracker):
        asset_tracker.register_asset(
            "eric", "2006 Toyota Camry", "camry",
            AssetCategory.VEHICLE, original_value=Decimal("4500"),
        )
        result = asset_tracker.record_depreciation(
            "camry", Decimal("500"), "Annual depreciation 2026",
        )
        assert result["book_value_after"] == "4000"
        assert result["total_costs"] == "500"

    def test_record_maintenance_from_owner(self, asset_tracker):
        asset_tracker.register_asset(
            "eric", "2006 Toyota Camry", "camry",
            AssetCategory.VEHICLE, original_value=Decimal("4500"),
        )
        result = asset_tracker.record_maintenance(
            "camry", Decimal("350"),
            "Key replacement and ignition repair",
            paid_from_slug="eric",
        )
        assert result["maintenance_cost"] == "350"
        assert result["asset"] == "camry"

    def test_record_insurance_premium(self, asset_tracker):
        asset_tracker.register_asset(
            "eric", "2006 Toyota Camry", "camry",
            AssetCategory.VEHICLE, original_value=Decimal("4500"),
        )
        result = asset_tracker.record_insurance_premium(
            "camry", Decimal("125"),
            "Monthly auto insurance — April 2026",
            policy_id="POL-AUTO-001",
        )
        assert result["premium"] == "125"

    def test_register_property(self, asset_tracker):
        result = asset_tracker.register_asset(
            "eric", "Wabash IN Property", "wabash-property",
            AssetCategory.PROPERTY, original_value=Decimal("85000"),
            metadata={"address_state": "IN"},
        )
        assert result["category"] == "property"
        assert result["book_value"] == "85000"

    def test_asset_summary(self, asset_tracker):
        asset_tracker.register_asset(
            "eric", "2006 Toyota Camry", "camry",
            AssetCategory.VEHICLE, original_value=Decimal("4500"),
        )
        asset_tracker.record_depreciation("camry", Decimal("500"))
        asset_tracker.record_maintenance("camry", Decimal("200"), "Oil change")
        asset_tracker.record_insurance_premium("camry", Decimal("125"), "Premium")

        summary = asset_tracker.get_asset_summary("camry")
        assert summary["category"] == "vehicle"
        assert summary["book_value"] == "4000"
        assert summary["cost_breakdown"]["depreciation"] == "500"
        assert summary["cost_breakdown"]["maintenance"] == "200"
        assert summary["cost_breakdown"]["insurance"] == "125"

    def test_list_assets(self, asset_tracker):
        asset_tracker.register_asset(
            "eric", "Camry", "camry",
            AssetCategory.VEHICLE, original_value=Decimal("4500"),
        )
        asset_tracker.register_asset(
            "eric", "Wabash Property", "wabash",
            AssetCategory.PROPERTY, original_value=Decimal("85000"),
        )
        assets = asset_tracker.list_assets("eric")
        slugs = {a["slug"] for a in assets}
        assert "camry" in slugs
        assert "wabash" in slugs
        assert len(assets) == 2
