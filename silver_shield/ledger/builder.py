"""
Excel ledger workbook builder.

Generates a multi-sheet Excel workbook with:
- Entity Register (account-to-entity mapping)
- Parent Debt Ledger (check deposit tracking)
- General Ledger (all transactions, double-entry)
- Account Summary (statement counts, balances)
- P&L per business entity
- Personal Financial Statement

Uses financial modeling color conventions:
  Blue = inputs, Black = formulas, Green = cross-sheet, Yellow = needs attention
"""

from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from ..config import Config, Entity


class LedgerBuilder:
    """Builds the financial ledger Excel workbook from config and extracted data."""

    def __init__(self, config: Config):
        self.config = config
        self.wb = Workbook()
        self._init_styles()

    def _init_styles(self):
        fmt = self.config.excel_format
        self.input_font = Font(color=fmt.input_color, name="Arial", size=10)
        self.formula_font = Font(color=fmt.formula_color, name="Arial", size=10)
        self.crossref_font = Font(color=fmt.crossref_color, name="Arial", size=10)
        self.bold_font = Font(bold=True, name="Arial", size=10)
        self.header_font = Font(bold=True, name="Arial", size=11, color=fmt.header_fg)
        self.gray_font = Font(name="Arial", size=9, color="666666")
        self.header_fill = PatternFill("solid", fgColor=fmt.header_bg)
        self.attention_fill = PatternFill("solid", fgColor=fmt.attention_bg)
        self.subtotal_fill = PatternFill("solid", fgColor="D9E1F2")
        self.border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin'),
        )
        self.currency_fmt = fmt.currency_format

    def build(self) -> Workbook:
        """Build all sheets."""
        # Remove default sheet
        self.wb.remove(self.wb.active)

        self._build_entity_register()
        self._build_parent_debt_ledger()
        self._build_general_ledger()
        self._build_account_summary()

        for entity in self.config.business_entities():
            self._build_pl(entity)

        self._build_personal_financial_stmt()

        return self.wb

    def save(self, path: Optional[str] = None):
        """Save workbook to file."""
        output = Path(path) if path else self.config.ledger_path
        output.parent.mkdir(parents=True, exist_ok=True)
        self.wb.save(str(output))
        return str(output)

    def _build_entity_register(self):
        """Entity Register sheet -- maps accounts to legal entities."""
        ws = self.wb.create_sheet("Entity Register")

        ws.cell(row=1, column=1, value="ENTITY REGISTER").font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=f"{self.config.case_name} | {self.config.case_number}").font = self.gray_font

        headers = ["Entity", "Type", "Account ID", "Institution", "Account Type", "Label", "Parser"]
        for i, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=i, value=h)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.border

        row = 5
        for entity in self.config.entities:
            for acct in entity.accounts:
                ws.cell(row=row, column=1, value=entity.name).font = self.formula_font
                ws.cell(row=row, column=2, value=entity.type).font = self.formula_font
                ws.cell(row=row, column=3, value=acct.id).font = self.input_font
                ws.cell(row=row, column=4, value=acct.institution).font = self.formula_font
                ws.cell(row=row, column=5, value=acct.type).font = self.formula_font
                ws.cell(row=row, column=6, value=acct.label).font = self.formula_font
                ws.cell(row=row, column=7, value=acct.parser).font = self.gray_font
                for c in range(1, 8):
                    ws.cell(row=row, column=c).border = self.border
                row += 1

    def _build_parent_debt_ledger(self):
        """Parent Debt Ledger -- tracks check deposits (possible family loans)."""
        ws = self.wb.create_sheet("Parent Debt Ledger")

        ws.cell(row=1, column=1, value="UNSECURED DEBT -- LOANS FROM FAMILY").font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=f"{self.config.case_name} | {self.config.case_number}").font = self.gray_font

        headers = ["Date", "Description", "From", "To Account", "Amount", "Running Total", "Source Document"]
        for i, h in enumerate(headers, 1):
            cell = ws.cell(row=5, column=i, value=h)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.border

        # Pre-fill 40 transaction rows with running total formulas
        for r in range(6, 46):
            ws.cell(row=r, column=5).number_format = self.currency_fmt
            ws.cell(row=r, column=6).number_format = self.currency_fmt
            for c in range(1, 8):
                ws.cell(row=r, column=c).border = self.border

            if r == 6:
                ws.cell(row=r, column=6, value='=E6').font = self.formula_font
            else:
                ws.cell(row=r, column=6, value=f'=IF(E{r}="","",F{r-1}+E{r})').font = self.formula_font

        # Total row
        ws.cell(row=47, column=1, value="TOTAL UNSECURED DEBT TO FAMILY").font = self.bold_font
        ws.cell(row=47, column=1).fill = self.subtotal_fill
        ws.cell(row=47, column=5, value='=SUM(E6:E46)').font = self.bold_font
        ws.cell(row=47, column=5).number_format = self.currency_fmt

    def _build_general_ledger(self):
        """General Ledger -- all transactions across all accounts."""
        ws = self.wb.create_sheet("General Ledger")

        ws.cell(row=1, column=1, value="GENERAL LEDGER").font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=f"{self.config.case_name} | {self.config.case_number}").font = self.gray_font

        headers = ["Date", "Account", "Entity", "Type", "Description", "Debit", "Credit", "Category", "Source"]
        for i, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=i, value=h)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.border

        # Data rows start at 5, will be populated by extract_all script

    def _build_account_summary(self):
        """Account Summary -- one row per account with key metrics."""
        ws = self.wb.create_sheet("Account Summary")

        ws.cell(row=1, column=1, value="ACCOUNT SUMMARY").font = Font(bold=True, size=14)

        headers = ["Account", "Entity", "Institution", "Type", "Label", "Status",
                    "Date Range", "Statements", "Opening Bal", "Closing Bal", "Notes"]
        for i, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=i, value=h)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.border

        row = 4
        for entity in self.config.entities:
            for acct in entity.accounts:
                ws.cell(row=row, column=1, value=acct.id).font = self.input_font
                ws.cell(row=row, column=2, value=entity.name).font = self.formula_font
                ws.cell(row=row, column=3, value=acct.institution).font = self.formula_font
                ws.cell(row=row, column=4, value=acct.type).font = self.formula_font
                ws.cell(row=row, column=5, value=acct.label).font = self.formula_font
                ws.cell(row=row, column=6, value="Active").font = self.formula_font
                ws.cell(row=row, column=9).number_format = self.currency_fmt
                ws.cell(row=row, column=10).number_format = self.currency_fmt
                for c in range(1, 12):
                    ws.cell(row=row, column=c).border = self.border
                row += 1

    def _build_pl(self, entity: Entity):
        """P&L sheet for a business entity."""
        sheet_name = f"{entity.name} P&L"
        if len(sheet_name) > 31:
            sheet_name = sheet_name[:31]
        ws = self.wb.create_sheet(sheet_name)

        ws.cell(row=1, column=1, value=f"{entity.name} -- PROFIT & LOSS").font = Font(bold=True, size=14)

        # Revenue section
        ws.cell(row=4, column=1, value="REVENUE").font = self.bold_font
        ws.cell(row=5, column=1, value="Gross Receipts").font = self.formula_font
        ws.cell(row=6, column=1, value="Other Income").font = self.formula_font
        ws.cell(row=7, column=1, value="TOTAL REVENUE").font = self.bold_font
        ws.cell(row=7, column=1).fill = self.subtotal_fill

        # Expense section
        ws.cell(row=9, column=1, value="EXPENSES").font = self.bold_font
        ws.cell(row=10, column=1, value="Operating Expenses").font = self.formula_font
        ws.cell(row=11, column=1, value="Management Compensation").font = self.formula_font
        ws.cell(row=12, column=1, value="Tax Payments").font = self.formula_font
        ws.cell(row=13, column=1, value="Other Expenses").font = self.formula_font
        ws.cell(row=14, column=1, value="TOTAL EXPENSES").font = self.bold_font
        ws.cell(row=14, column=1).fill = self.subtotal_fill

        # Net income
        ws.cell(row=16, column=1, value="NET INCOME").font = Font(bold=True, size=12)

        # Account balances
        ws.cell(row=18, column=1, value="ACCOUNT BALANCES").font = self.bold_font
        row = 19
        for acct in entity.accounts:
            ws.cell(row=row, column=1, value=f"{acct.label} ({acct.id})").font = self.formula_font
            ws.cell(row=row, column=2).number_format = self.currency_fmt
            ws.cell(row=row, column=3).number_format = self.currency_fmt
            row += 1
        ws.cell(row=row, column=1, value="TOTAL BUSINESS CASH").font = self.bold_font
        ws.cell(row=row, column=1).fill = self.subtotal_fill

    def _build_personal_financial_stmt(self):
        """Personal Financial Statement -- assets and liabilities."""
        ws = self.wb.create_sheet("Personal Financial Stmt")

        ws.cell(row=1, column=1, value="PERSONAL FINANCIAL STATEMENT").font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=f"{self.config.case_name} | {self.config.case_number}").font = self.gray_font

        # Assets
        ws.cell(row=4, column=1, value="ASSETS").font = Font(bold=True, size=12)
        asset_headers = ["Asset", "Description", "Current Value", "DOM Value", "Separate/Marital", "Notes"]
        for i, h in enumerate(asset_headers, 1):
            cell = ws.cell(row=5, column=i, value=h)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.border

        # Pre-fill asset rows
        row = 6
        for entity in self.config.personal_entities():
            for acct in entity.accounts:
                ws.cell(row=row, column=1, value=f"{acct.institution} {acct.id}").font = self.formula_font
                ws.cell(row=row, column=2, value=acct.label).font = self.formula_font
                ws.cell(row=row, column=3).number_format = self.currency_fmt
                ws.cell(row=row, column=3).fill = self.attention_fill
                for c in range(1, 7):
                    ws.cell(row=row, column=c).border = self.border
                row += 1

        # Total assets
        total_row = row
        ws.cell(row=total_row, column=1, value="TOTAL ASSETS").font = self.bold_font
        ws.cell(row=total_row, column=1).fill = self.subtotal_fill
        ws.cell(row=total_row, column=3, value=f'=SUM(C6:C{total_row-1})').font = self.bold_font
        ws.cell(row=total_row, column=3).number_format = self.currency_fmt

        # Liabilities
        liab_start = total_row + 2
        ws.cell(row=liab_start, column=1, value="LIABILITIES").font = Font(bold=True, size=12)
        liab_headers = ["Liability", "Creditor", "Balance Owed", "Monthly Payment", "Secured/Unsecured", "Notes"]
        for i, h in enumerate(liab_headers, 1):
            cell = ws.cell(row=liab_start + 1, column=i, value=h)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.border

        liab_data_start = liab_start + 2
        liab_rows = [
            "Attorney Fees", "Credit Cards", "Parent/Family Loans",
            "Medical/Evaluator", "Supervised Visitation", "Legal Costs", "Other",
        ]
        for i, name in enumerate(liab_rows):
            r = liab_data_start + i
            ws.cell(row=r, column=1, value=name).font = self.formula_font
            ws.cell(row=r, column=3).number_format = self.currency_fmt
            ws.cell(row=r, column=3).fill = self.attention_fill
            for c in range(1, 7):
                ws.cell(row=r, column=c).border = self.border

        # Parent loans cross-ref
        parent_row = liab_data_start + 2  # "Parent/Family Loans"
        ws.cell(row=parent_row, column=3, value="='Parent Debt Ledger'!E47").font = self.crossref_font
        ws.cell(row=parent_row, column=3).fill = PatternFill()

        # Total liabilities
        total_liab_row = liab_data_start + len(liab_rows)
        ws.cell(row=total_liab_row, column=1, value="TOTAL LIABILITIES").font = self.bold_font
        ws.cell(row=total_liab_row, column=1).fill = self.subtotal_fill
        ws.cell(row=total_liab_row, column=3,
                value=f'=SUM(C{liab_data_start}:C{total_liab_row-1})').font = self.bold_font
        ws.cell(row=total_liab_row, column=3).number_format = self.currency_fmt

        # Net worth
        nw_row = total_liab_row + 2
        ws.cell(row=nw_row, column=1, value="NET WORTH (Assets - Liabilities)").font = Font(bold=True, size=12)
        ws.cell(row=nw_row, column=3, value=f'=C{total_row}-C{total_liab_row}').font = Font(bold=True, size=12)
        ws.cell(row=nw_row, column=3).number_format = self.currency_fmt
