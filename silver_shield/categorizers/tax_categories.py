"""
IRS Form 1120 tax category mapping with confidence scoring.

Every transaction gets:
  - tax_category: maps to a Form 1120 line item
  - confidence: HIGH / MEDIUM / LOW
  - form_line: the actual IRS line reference
  - is_transfer: True if inter-account transfer (eliminated on consolidation)
"""

import re
from dataclasses import dataclass

# Zoseco inter-account IDs for transfer detection
ZOSECO_ACCOUNTS = {"x4981", "x9270", "x9327", "x9633", "x6926", "x7008"}


@dataclass
class TaxCategory:
    category: str
    form_line: str
    confidence: str  # HIGH, MEDIUM, LOW
    is_transfer: bool = False
    review_note: str = ""


# Rules: (compiled_regex, category, form_line, confidence, is_transfer, note)
# Evaluated in order — first match wins. More specific rules first.
RULES = [
    # === INTERNAL TRANSFERS (eliminate on consolidation) ===
    (r"(?i)xfer\s+(income|profit|tax|mgmt|owncomp|owner\s*comp|own\.comp)\s+to\s+(opex|income|profit|tax|mgmt|owncomp|owner)",
     "TRANSFER_INTERNAL", "N/A", "HIGH", True, "Zoseco internal allocation"),
    (r"(?i)INTERNET TRANSFER FROM CHK\s*\d+\s+TO CHK\s*\d+",
     "TRANSFER_INTERNAL", "N/A", "HIGH", True, "Zoseco internal transfer"),
    (r"(?i)MOBILE TRANSFER FROM CHK\s*\d+\s+TO CHK\s*\d+",
     "TRANSFER_INTERNAL", "N/A", "HIGH", True, "Zoseco internal transfer"),
    (r"(?i)CENTIER EXT TRNSFR",
     "TRANSFER_EXTERNAL", "N/A", "MEDIUM", True, "External bank transfer — verify destination"),
    (r"(?i)USAA FUNDS TRANSFER",
     "TRANSFER_EXTERNAL", "N/A", "MEDIUM", True, "USAA inter-account transfer"),

    # === REVENUE (Form 1120 Line 1a) ===
    (r"(?i)STRIPE\s+TRANSFER", "REVENUE", "1a", "HIGH", False, ""),
    (r"(?i)SQUARE\s+INC", "REVENUE", "1a", "HIGH", False, ""),
    (r"(?i)WIRE\s+TRANSFER\s+FROM", "REVENUE", "1a", "HIGH", False, "Client wire payment"),
    (r"(?i)APARTMENTS\.COM|COZY\s+SERVICES", "REVENUE_TEST", "1a", "LOW", False, "Platform test deposit? Verify if real revenue"),
    (r"(?i)VEHICLE\s+MANAGEME", "REVENUE_TEST", "1a", "LOW", False, "Platform test? Verify"),

    # === OFFICER COMPENSATION (Form 1120 Line 12) ===
    (r"(?i)xfer\s+income\s+to\s+owner", "OFFICER_COMP", "12", "HIGH", False, "Owner compensation draw"),
    (r"(?i)xfer\s+income\s+to\s+own\.comp", "OFFICER_COMP", "12", "HIGH", False, "Owner compensation draw"),
    (r"(?i)xfer\s+income\s+to\s+owncomp", "OFFICER_COMP", "12", "HIGH", False, "Owner compensation draw"),

    # === PAYROLL (Form 1120 Lines 13, 17) ===
    (r"(?i)GUSTO\s+NET", "PAYROLL_WAGES", "13", "HIGH", False, "Net payroll disbursement"),
    (r"(?i)GUSTO\s+TAX", "PAYROLL_TAX", "17", "HIGH", False, "Payroll tax payment"),
    (r"(?i)GUSTO\s+FEE", "PAYROLL_FEES", "26", "HIGH", False, "Payroll service fee"),
    (r"(?i)GUSTO\s+TLR", "PAYROLL_REFUND", "13", "HIGH", False, "Gusto tax liability refund"),

    # === ADVERTISING (Form 1120 Line 20) ===
    (r"(?i)GOOGLE\s+ADS", "ADVERTISING", "20", "HIGH", False, ""),
    (r"(?i)FACEBK|FACEBOOK", "ADVERTISING", "20", "HIGH", False, ""),
    (r"(?i)INDEED", "ADVERTISING", "20", "HIGH", False, "Job posting / recruitment ad"),
    (r"(?i)CRAIGSLIST", "ADVERTISING", "20", "HIGH", False, ""),
    (r"(?i)X\s+CORP.*PAID\s+FEA", "ADVERTISING", "20", "HIGH", False, "Twitter/X advertising"),

    # === UTILITIES (Form 1120 Line 26 - Other Deductions) ===
    (r"(?i)NIPSCO", "UTILITIES", "26", "HIGH", False, "Gas/electric utility"),
    (r"(?i)NITCO", "UTILITIES", "26", "HIGH", False, "Internet service"),
    (r"(?i)T-MOBILE", "UTILITIES", "26", "HIGH", False, "Mobile phone"),
    (r"(?i)XCEL\s+ENERGY", "UTILITIES", "26", "HIGH", False, "Electric utility"),
    (r"(?i)REPUBLIC\s+SERVICES\s+TRASH", "UTILITIES", "26", "HIGH", False, "Trash service"),

    # === SOFTWARE & SAAS (Form 1120 Line 26) ===
    (r"(?i)GOOGLE\s+(WORKSPACE|GSUITE)", "SOFTWARE", "26", "HIGH", False, "Business email/docs"),
    (r"(?i)XERO\s+US", "SOFTWARE", "26", "HIGH", False, "Accounting software"),
    (r"(?i)SPOTIFY", "SOFTWARE", "26", "MEDIUM", False, "Music subscription — verify business use"),
    (r"(?i)SQUARESPACE|SQSP", "SOFTWARE", "26", "HIGH", False, "Website hosting"),
    (r"(?i)ZAPIER", "SOFTWARE", "26", "HIGH", False, "Automation platform"),
    (r"(?i)ZAPRITE", "SOFTWARE", "26", "HIGH", False, "Bitcoin payment platform"),
    (r"(?i)NAME-?CHEAP", "SOFTWARE", "26", "HIGH", False, "Domain registration"),
    (r"(?i)ANTHROPIC|CLAUDE\.AI", "SOFTWARE", "26", "HIGH", False, "AI tool subscription"),
    (r"(?i)VENICE\.AI", "SOFTWARE", "26", "HIGH", False, "AI tool"),
    (r"(?i)SPHEREMAIL", "SOFTWARE", "26", "HIGH", False, "Email service"),
    (r"(?i)GOOGLE\s+WYZE", "SOFTWARE", "26", "MEDIUM", False, "Smart home app — verify business use"),

    # === PROFESSIONAL SERVICES (Form 1120 Line 26) ===
    (r"(?i)BURKE\s+COSTANZA", "PROFESSIONAL_LEGAL", "26", "HIGH", False, "Legal fees"),
    (r"(?i)RHAME\s+ELWOOD", "PROFESSIONAL_LEGAL", "26", "HIGH", False, "Legal fees"),
    (r"(?i)EPN\s+EXPERIAN", "PROFESSIONAL", "26", "HIGH", False, "Business credit monitoring"),
    (r"(?i)RUNNING\s+CREEK", "PROFESSIONAL_COUNSELING", "26", "HIGH", False, "Counseling services"),
    (r"(?i)23\s+PROSE\s+EFILE", "PROFESSIONAL_LEGAL", "26", "HIGH", False, "Court e-filing fee"),

    # === OFFICE & SHIPPING (Form 1120 Line 26) ===
    (r"(?i)STAPLES", "OFFICE_SUPPLIES", "26", "HIGH", False, ""),
    (r"(?i)OFFICE\s+DEPOT", "OFFICE_SUPPLIES", "26", "HIGH", False, ""),
    (r"(?i)USPS\s+PO", "SHIPPING", "26", "HIGH", False, "Postage"),
    (r"(?i)POSTAL\s+ANNEX", "SHIPPING", "26", "HIGH", False, "Shipping/mailing service"),
    (r"(?i)BARNES.*NOBLE", "OFFICE_SUPPLIES", "26", "MEDIUM", False, "Books — verify business use"),

    # === TRAVEL & MEALS (Form 1120 Line 26, subject to limits) ===
    (r"(?i)SOUTHWEST|SOUTHWES\s+\d", "TRAVEL", "26", "HIGH", False, "Airfare"),
    (r"(?i)AIRBNB", "TRAVEL_LODGING", "26", "HIGH", False, "Business lodging"),
    (r"(?i)HIDEAWAY\s+MOUNTAIN", "TRAVEL_LODGING", "26", "MEDIUM", False, "Lodging — verify business purpose"),
    (r"(?i)KALADI\s+COFFEE", "MEALS", "26", "MEDIUM", False, "Meals — 50% deductible"),
    (r"(?i)MANGO\s+TREE", "MEALS", "26", "MEDIUM", False, "Meals — 50% deductible"),
    (r"(?i)NIXONS\s+COFFEE", "MEALS", "26", "MEDIUM", False, "Meals — 50% deductible"),
    (r"(?i)UNCLE\s+JULIO", "MEALS", "26", "MEDIUM", False, "Meals — 50% deductible"),
    (r"(?i)COE\s+REC\s+CENTER", "PERSONAL", "N/A", "MEDIUM", False, "Gym/rec — likely personal"),
    (r"(?i)ALPINE\s+CHORALE", "PERSONAL", "N/A", "MEDIUM", False, "Music group — likely personal"),
    (r"(?i)NATIONAL\s+WESTERN\s+STOCK", "ENTERTAINMENT", "26", "LOW", False, "Stock show — verify business purpose"),

    # === RETAIL / MIXED USE (need review) ===
    (r"(?i)HOME\s+DEPOT", "SUPPLIES", "26", "MEDIUM", False, "Hardware — verify business vs personal"),
    (r"(?i)BEST\s+BUY", "EQUIPMENT", "26", "MEDIUM", False, "Electronics — verify business use"),
    (r"(?i)AMAZON", "SUPPLIES", "26", "MEDIUM", False, "Online purchase — verify business use"),
    (r"(?i)WAL-?MART|WM\s+SUPERCENTER", "SUPPLIES", "26", "LOW", False, "Retail — could be personal or business"),
    (r"(?i)TARGET\s+T-", "SUPPLIES", "26", "LOW", False, "Retail — could be personal or business"),
    (r"(?i)COSTCO", "SUPPLIES", "26", "LOW", False, "Wholesale — could be personal or business"),
    (r"(?i)SAFEWAY", "GROCERIES", "N/A", "LOW", False, "Grocery — likely personal unless client meeting"),
    (r"(?i)NATURAL\s+GROCERS", "GROCERIES", "N/A", "LOW", False, "Grocery — likely personal"),
    (r"(?i)ALDI", "GROCERIES", "N/A", "LOW", False, "Grocery — likely personal"),
    (r"(?i)MICRO\s+ELECTRONIC", "EQUIPMENT", "26", "MEDIUM", False, "Electronics — verify business use"),
    (r"(?i)ETSY", "SUPPLIES", "26", "LOW", False, "Online marketplace — verify business use"),
    (r"(?i)SQ\s+THE\s+SPACE", "RENT_COWORK", "26", "HIGH", False, "Coworking space"),

    # === CRYPTO ===
    (r"(?i)KRAKEN", "CRYPTO", "N/A", "HIGH", False, "Crypto exchange transaction"),
    (r"(?i)COINBASE", "CRYPTO", "N/A", "HIGH", False, "Crypto exchange"),

    # === BANK FEES ===
    (r"(?i)OVERDRAFT\s+FEE", "BANK_FEES", "26", "HIGH", False, ""),
    (r"(?i)DORMANT\s+ACCOUNT\s+FEE", "BANK_FEES", "26", "HIGH", False, ""),
    (r"(?i)FEE\s+REVERSAL", "BANK_FEE_REVERSAL", "26", "HIGH", False, ""),
    (r"(?i)Charged\s+off", "BANK_FEES", "26", "HIGH", False, "Account closure charge-off"),
    (r"(?i)WIRE\s+TRANSFER\s+FEE", "BANK_FEES", "26", "HIGH", False, ""),

    # === INTEREST ===
    (r"(?i)INTEREST\s+PAID|IOD\s+INTEREST", "INTEREST_INCOME", "5", "HIGH", False, "Bank interest earned"),

    # === INSURANCE ===
    (r"(?i)P&C\s+USAA\s+SUBSCR", "INSURANCE", "26", "HIGH", False, "Property & casualty insurance"),
    (r"(?i)VENMO\s+PAYMENT", "TRANSFER_PEER", "N/A", "LOW", False, "Peer payment — verify purpose"),
    (r"(?i)CASH\s+APP", "TRANSFER_PEER", "N/A", "MEDIUM", False, "Cash App — verify purpose"),

    # === IRS ===
    (r"(?i)IRS\s+TREAS.*TAX\s+REF", "TAX_REFUND", "N/A", "HIGH", False, "IRS tax refund"),

    # === RENT ===
    (r"(?i)PAYPAL\s+VALPARAISOR", "RENT", "26", "MEDIUM", False, "PayPal — possibly rent payment"),

    # === GENERIC DEPOSITS (need review) ===
    (r"(?i)^DEPOSIT$", "DEPOSIT_UNCLASSIFIED", "N/A", "LOW", False, "Generic deposit — could be client check, parent loan, or cash deposit. NEEDS REVIEW."),
    (r"(?i)LINK\.COM\s+CASH\s+BACK", "OTHER_INCOME", "10", "HIGH", False, "Cash back reward"),

    # === CHECKS ===
    (r"(?i)CHECK\s+#", "CHECK_WRITTEN", "26", "LOW", False, "Check — payee unknown from bank data. NEEDS REVIEW."),
]

# Compile regexes once
_COMPILED_RULES = [(re.compile(pattern), cat, line, conf, is_xfer, note)
                   for pattern, cat, line, conf, is_xfer, note in RULES]


def categorize_transaction(description: str, account_id: str = "",
                           txn_type: str = "", amount: float = 0) -> TaxCategory:
    """Categorize a single transaction against IRS Form 1120 lines."""
    for regex, category, form_line, confidence, is_transfer, note in _COMPILED_RULES:
        if regex.search(description):
            # Boost transfer confidence if we can confirm both accounts are Zoseco
            if is_transfer and account_id in ZOSECO_ACCOUNTS:
                confidence = "HIGH"
            return TaxCategory(
                category=category,
                form_line=form_line,
                confidence=confidence,
                is_transfer=is_transfer,
                review_note=note,
            )

    # Fallback
    return TaxCategory(
        category="UNCATEGORIZED",
        form_line="N/A",
        confidence="LOW",
        review_note=f"No matching rule. Description: {description[:60]}",
    )
