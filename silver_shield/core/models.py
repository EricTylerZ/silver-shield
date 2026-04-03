"""
Silver Shield core data models.

Four primitives that compose into a fractal accounting system:
  Entity  -- anything that can have books (person, business, project, agent)
  Account -- a named container for one currency belonging to one entity
  Currency -- a unit of account (USD, XAG, MERIT, BTC, ETH, ...)
  Entry   -- an append-only ledger line, always part of a double-entry pair

Design principles:
  - Every entity chain terminates at a human (subsidiarity)
  - Entries are never modified or deleted (append-only)
  - Double-entry: every transaction creates a debit and credit of equal amount
  - balance_after is denormalized for read performance (EZ Merit pattern)
  - Idempotency keys prevent duplicate entries
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    PERSON = "person"
    BUSINESS = "business"
    PROJECT = "project"
    AGENT = "agent"


class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"
    EQUITY = "equity"


class EntryType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class RateSource(str, Enum):
    FIXED = "fixed"             # rate = 1.0 always (base currency)
    SILVER_ORACLE = "silver"    # community-shield /api/silver/spot
    CRYPTO_ORACLE = "crypto"    # CoinGecko
    NONE = "none"               # not convertible (merit points)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

@dataclass
class Authorization:
    """
    Proof of authority for a ledger entry.

    Like military orders -- nothing moves without a signed order on file.
    Every ledger action (mint, allocation, correction, spend) must carry
    one of these: who said so, in what words, and where that's on record.
    """
    authorized_by: str          # slug of the authorizing entity (must trace to human)
    statement: str              # what they said -- the actual words of the order
    reference: str              # where it's on record (CI number, commit, conversation URL)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "authorized_by": self.authorized_by,
            "statement": self.statement,
            "reference": self.reference,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Authorization":
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            authorized_by=data["authorized_by"],
            statement=data["statement"],
            reference=data["reference"],
            timestamp=ts or datetime.now(),
        )


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

@dataclass
class Currency:
    """A unit of account."""
    code: str               # ISO-style: "USD", "XAG", "MERIT", "BTC", "ETH"
    name: str               # "US Dollar", "Silver (Troy Oz)", ...
    symbol: str             # "$", "oz", "MP", "BTC", "ETH"
    precision: int          # decimal places: 2 for USD, 4 for XAG, 0 for MERIT, 8 for BTC
    is_convertible: bool = True     # False for MERIT (site-sovereign per Stewardship Exchange)
    rate_source: RateSource = RateSource.FIXED

    def format(self, amount: Decimal) -> str:
        """Format an amount in this currency."""
        quantized = amount.quantize(Decimal(10) ** -self.precision)
        if self.symbol in ("$",):
            return f"{self.symbol}{quantized:,}"
        return f"{quantized:,} {self.symbol}"


# Default currencies
CURRENCIES = {
    "USD": Currency("USD", "US Dollar", "$", 2, True, RateSource.FIXED),
    "XAG": Currency("XAG", "Silver (Troy Oz)", "oz", 4, True, RateSource.SILVER_ORACLE),
    "MERIT": Currency("MERIT", "EZ Merit Points", "MP", 0, False, RateSource.NONE),
    "BTC": Currency("BTC", "Bitcoin", "BTC", 8, True, RateSource.CRYPTO_ORACLE),
    "ETH": Currency("ETH", "Ethereum", "ETH", 8, True, RateSource.CRYPTO_ORACLE),
}


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    """
    Anything that can have books.

    Forms a tree via parent_id. Every chain must terminate at a person
    (human_authority). An agent unto itself is not acceptable -- there
    is always a human at the top.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    slug: str = ""
    name: str = ""
    entity_type: EntityType = EntityType.PERSON
    parent_id: Optional[str] = None         # None only for root human
    human_authority: Optional[str] = None   # denormalized: always the root person's id
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def is_root(self) -> bool:
        return self.parent_id is None

    def is_human(self) -> bool:
        return self.entity_type == EntityType.PERSON


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

@dataclass
class Account:
    """
    A named container for one currency belonging to one entity.

    Account types follow standard accounting:
      asset     -- what you own (bank accounts, crypto holdings, receivables)
      liability -- what you owe (loans, parent debt, payables)
      income    -- money coming in (payroll, business income, interest)
      expense   -- money going out (operating costs, API usage, transfers)
      equity    -- owner's stake (net worth, retained earnings)

    The normal balance direction:
      asset/expense  -> debit increases, credit decreases
      liability/income/equity -> credit increases, debit decreases
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str = ""
    currency_code: str = "USD"
    account_type: AccountType = AccountType.ASSET
    name: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    @property
    def normal_balance(self) -> EntryType:
        """Which side increases this account's balance."""
        if self.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            return EntryType.DEBIT
        return EntryType.CREDIT


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    """
    An append-only ledger line.

    Part of a double-entry transaction: every Entry has a sibling with
    the opposite entry_type and the same transaction_id. The pair's
    amounts are always equal.

    Never modified or deleted.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str = ""
    transaction_id: str = ""        # links debit + credit entries
    entry_type: EntryType = EntryType.DEBIT
    amount: Decimal = Decimal("0")  # always positive
    balance_after: Decimal = Decimal("0")   # denormalized running balance
    description: str = ""
    entry_date: date = field(default_factory=date.today)
    created_at: datetime = field(default_factory=datetime.now)
    reference_id: Optional[str] = None      # links to source (statement, merit entry, etc.)
    source_system: Optional[str] = None     # "bank_import", "manual", "ez_merit", "auto_agent"
    idempotency_key: Optional[str] = None   # prevents duplicates
    authorization: Optional[Authorization] = None  # who said so, in what words, where on record
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.amount, (int, float, str)):
            self.amount = Decimal(str(self.amount))
        if isinstance(self.balance_after, (int, float, str)):
            self.balance_after = Decimal(str(self.balance_after))
        if isinstance(self.entry_date, str):
            self.entry_date = date.fromisoformat(self.entry_date)
        if self.amount < 0:
            raise ValueError("Entry amount must be non-negative")
        if isinstance(self.authorization, dict):
            self.authorization = Authorization.from_dict(self.authorization)


# ---------------------------------------------------------------------------
# Transaction (convenience wrapper -- not stored separately)
# ---------------------------------------------------------------------------

@dataclass
class Transaction:
    """
    A double-entry transaction: one debit and one credit.
    Not persisted as its own record -- the two Entry objects
    carry the transaction_id that links them.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    debit_account_id: str = ""
    credit_account_id: str = ""
    amount: Decimal = Decimal("0")
    description: str = ""
    entry_date: date = field(default_factory=date.today)
    reference_id: Optional[str] = None
    source_system: Optional[str] = None
    idempotency_key: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.amount, (int, float, str)):
            self.amount = Decimal(str(self.amount))


# ---------------------------------------------------------------------------
# Exchange Rate
# ---------------------------------------------------------------------------

@dataclass
class ExchangeRate:
    """A recorded exchange rate between two currencies."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_currency: str = ""
    to_currency: str = ""
    rate: Decimal = Decimal("1")
    source: str = ""
    recorded_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if isinstance(self.rate, (int, float, str)):
            self.rate = Decimal(str(self.rate))
