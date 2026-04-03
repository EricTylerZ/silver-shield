"""
Centier Bank statement extractor.

Centier statements have a columnar format where DATE+DESCRIPTION appear in one
column block and AMOUNT in a separate column block. This requires a two-phase
parser: collect date+desc entries and amounts separately, then zip them together.

The summary block also has a non-standard format where labels (BEGINNING BALANCE,
DEPOSITS AND OTHER CREDITS, etc.) appear on separate lines from the $ symbols
and amounts.
"""

import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

import pdfplumber

from .base import BaseExtractor, Statement, Transaction


class CentierExtractor(BaseExtractor):
    """Extracts transactions from Centier bank statement PDFs."""

    def extract(self, pdf_path: str) -> Optional[Statement]:
        """Extract all transactions from a Centier statement PDF."""
        fname = Path(pdf_path).name

        # Parse period from filename: "Account x1234 MM-DD-YY-MM-DD-YY.pdf"
        m = re.search(r'(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', fname)
        if m:
            sm, sd, sy, em, ed, ey = m.groups()
            start = datetime(2000 + int(sy), int(sm), int(sd))
            end = datetime(2000 + int(ey), int(em), int(ed))
        else:
            # Also accept renamed format: "Centier_x1234_YYYY-MM-DD_to_YYYY-MM-DD_Statement.pdf"
            m = re.search(r'(\d{4})-(\d{2})-(\d{2})_to_(\d{4})-(\d{2})-(\d{2})', fname)
            if m:
                sy, sm, sd, ey, em, ed = m.groups()
                start = datetime(int(sy), int(sm), int(sd))
                end = datetime(int(ey), int(em), int(ed))
            else:
                # Last resort: extract dates from PDF text content
                text = self._extract_text_pdfplumber(pdf_path)
                if not text:
                    text = self._extract_text_pdftotext(pdf_path)
                dm = re.search(r'FROM\s+(\d{2}/\d{2}/\d{2})\s+THRU\s+(\d{2}/\d{2}/\d{2})', text or '')
                if not dm:
                    return None
                start = datetime.strptime(dm.group(1), "%m/%d/%y")
                end = datetime.strptime(dm.group(2), "%m/%d/%y")

        # Try pdfplumber first (works for text-based PDFs)
        text = self._extract_text_pdfplumber(pdf_path)
        if not text or len(text) < 50:
            # Fallback to pdftotext (handles columnar format better sometimes)
            text = self._extract_text_pdftotext(pdf_path)

        if not text or len(text) < 50:
            return None

        stmt = Statement(
            file_name=fname,
            account_id=self.account_id,
            period_start=start.strftime('%Y-%m-%d'),
            period_end=end.strftime('%Y-%m-%d'),
        )

        # Extract statement totals
        m = re.search(r'DEPOSITS AND OTHER CREDITS\s*\+\s*([\d,]+\.\d{2})', text)
        if m:
            stmt.deposits_total = float(m.group(1).replace(',', ''))

        m = re.search(r'CHECKS AND OTHER DEBITS\s*-\s*([\d,]+\.\d{2})', text)
        if m:
            stmt.withdrawals_total = float(m.group(1).replace(',', ''))

        m = re.search(r'BEGINNING BALANCE.*?\$\s*([\d,]+\.\d{2})', text)
        if m:
            stmt.opening_balance = float(m.group(1).replace(',', ''))

        m = re.search(r'ENDING BALANCE.*?\$\s*([\d,]+\.\d{2})', text)
        if m:
            stmt.closing_balance = float(m.group(1).replace(',', ''))

        # Parse transactions by section
        self._parse_sections(text, stmt, start, end)

        # Validate
        self.validate_statement(stmt)

        return stmt

    def _extract_text_pdfplumber(self, pdf_path: str) -> str:
        try:
            pdf = pdfplumber.open(pdf_path)
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
            pdf.close()
            return text
        except Exception:
            return ""

    def _extract_text_pdftotext(self, pdf_path: str) -> str:
        try:
            r = subprocess.run(
                ['pdftotext', '-layout', pdf_path, '-'],
                capture_output=True, text=True, timeout=30,
            )
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""

    def _parse_sections(self, text: str, stmt: Statement,
                        start: datetime, end: datetime):
        """Parse deposit and withdrawal sections from statement text."""
        year = end.year
        lines = text.split('\n')
        current_section = None

        for line in lines:
            stripped = line.strip()
            upper = stripped.upper()

            # Detect section boundaries
            if 'DEPOSITS AND OTHER CREDITS' in upper and '+' not in stripped:
                current_section = 'deposit'
                continue
            if 'ELECTRONIC AND OTHER WITHDRAWALS' in upper:
                current_section = 'withdrawal'
                continue
            if 'CHECKS POSTED' in upper or 'CHECK REGISTER' in upper:
                current_section = 'check'
                continue
            if any(m in upper for m in ['DAILY BALANCE', 'ACCOUNT NUMBER:',
                                         'STATEMENT DATE:']):
                current_section = None
                continue
            if upper in ['DATE DESCRIPTION AMOUNT', '']:
                continue

            if not current_section:
                continue

            # Skip check register header line
            if upper.startswith('CHECK NO'):
                continue

            date_str = None
            desc = None
            amount = None

            # Standard: MM/DD description amount
            m = re.match(r'^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', stripped)
            if m:
                date_str, desc, amount = m.group(1), m.group(2).strip(), float(m.group(3).replace(',', ''))

            # Check register: one or more checks per line
            # Single: "1123 07/30 300.00"
            # Multi:  "6075 09/08 600.00 *6086 09/13 2,000.00 6087 09/30 900.00"
            if not date_str and current_section == 'check':
                check_matches = list(re.finditer(
                    r'(\*?\d+)\s+(\d{2}/\d{2})\s+([\d,]+\.\d{2})',
                    stripped
                ))
                for cm in check_matches:
                    check_no = cm.group(1).lstrip('*')
                    c_date = cm.group(2)
                    c_amount = float(cm.group(3).replace(',', ''))
                    c_month = int(c_date.split('/')[0])
                    c_day = int(c_date.split('/')[1])
                    c_year = year
                    if start.month > end.month and c_month >= start.month:
                        c_year = year - 1
                    c_full_date = f"{c_year}-{c_month:02d}-{c_day:02d}"

                    txn = Transaction(
                        date=c_full_date,
                        description=f"CHECK #{check_no}",
                        amount=c_amount,
                        type='withdrawal',
                    )
                    stmt.withdrawals.append(txn)
                    stmt.all_transactions.append(txn)
                if check_matches:
                    continue

            if date_str and amount is not None:
                month = int(date_str.split('/')[0])
                day = int(date_str.split('/')[1])
                txn_year = year
                if start.month > end.month and month >= start.month:
                    txn_year = year - 1
                full_date = f"{txn_year}-{month:02d}-{day:02d}"

                txn = Transaction(
                    date=full_date,
                    description=desc or "Unknown",
                    amount=amount,
                    type='deposit' if current_section == 'deposit' else 'withdrawal',
                )

                if current_section == 'deposit':
                    stmt.deposits.append(txn)
                else:
                    stmt.withdrawals.append(txn)
                stmt.all_transactions.append(txn)


class CentierColumnarExtractor(CentierExtractor):
    """
    Variant for Centier statements where pdftotext renders columns separately.

    Uses a two-phase approach:
    1. Collect date+description entries from left column
    2. Collect amounts from right column
    3. Zip them together

    Use this when CentierExtractor produces low transaction counts.
    """

    def _parse_sections(self, text: str, stmt: Statement,
                        start: datetime, end: datetime):
        """Two-phase columnar parser."""
        year = end.year
        lines = text.split('\n')

        # Phase 1: Find sections and collect entries
        current_section = None
        date_desc_entries = []
        amounts = []

        for line in lines:
            stripped = line.strip()
            upper = stripped.upper()

            # Section detection
            if 'DEPOSITS AND OTHER CREDITS' in upper:
                # Check if it's the summary line (has +) or section header
                if '+' in stripped:
                    continue
                current_section = 'deposit'
                date_desc_entries = []
                amounts = []
                continue

            if 'ELECTRONIC AND OTHER WITHDRAWALS' in upper:
                # Flush deposit section
                self._zip_and_add(date_desc_entries, amounts, stmt, start, end, 'deposit')
                current_section = 'withdrawal'
                date_desc_entries = []
                amounts = []
                continue

            if any(m in upper for m in ['DAILY BALANCE', 'CHECKS POSTED']):
                self._zip_and_add(date_desc_entries, amounts, stmt, start, end,
                                  current_section or 'withdrawal')
                current_section = None
                date_desc_entries = []
                amounts = []
                continue

            if not current_section:
                continue

            # Standalone amount
            amt_match = re.match(r'^[\d,]+\.\d{2}$', stripped.replace(' ', ''))
            if amt_match:
                amounts.append(float(stripped.replace(' ', '').replace(',', '')))
                continue

            # Date + description (possibly with amount on same line)
            m = re.match(r'^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', stripped)
            if m:
                date_desc_entries.append((m.group(1), m.group(2).strip()))
                amounts.append(float(m.group(3).replace(',', '')))
                continue

            m = re.match(r'^(\d{2}/\d{2})\s+(.+)$', stripped)
            if m:
                date_desc_entries.append((m.group(1), m.group(2).strip()))
                continue

        # Flush remaining
        if current_section and date_desc_entries:
            self._zip_and_add(date_desc_entries, amounts, stmt, start, end, current_section)

    def _zip_and_add(self, date_descs, amounts, stmt, start, end, section_type):
        """Zip date+description with amounts and add to statement."""
        year = end.year
        n = min(len(date_descs), len(amounts))
        for i in range(n):
            date_str, desc = date_descs[i]
            amount = amounts[i]

            month = int(date_str.split('/')[0])
            day = int(date_str.split('/')[1])
            txn_year = year
            if start.month > end.month and month >= start.month:
                txn_year = year - 1
            full_date = f"{txn_year}-{month:02d}-{day:02d}"

            txn = Transaction(
                date=full_date,
                description=desc,
                amount=amount,
                type='deposit' if section_type == 'deposit' else 'withdrawal',
            )

            if section_type == 'deposit':
                stmt.deposits.append(txn)
            else:
                stmt.withdrawals.append(txn)
            stmt.all_transactions.append(txn)
