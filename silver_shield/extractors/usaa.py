"""
USAA bank statement extractor.

USAA statements use a multi-line transaction format:
  MM/DD description $debit $credit $balance
  continuation line (more description)
  continuation line

Credits column has $X,XXX.XX format, debits same, with 0 for empty.
"""

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from .base import BaseExtractor, Statement, Transaction


class USAAExtractor(BaseExtractor):
    """Extracts transactions from USAA bank statement PDFs."""

    def extract(self, pdf_path: str) -> Optional[Statement]:
        """Extract all transactions from a USAA statement PDF."""
        fname = Path(pdf_path).name

        # Parse period from filename variants:
        # "USAA Checking x0000 2025 Jan.pdf"
        # "USAA Savings x0001 2025 Mar.pdf"
        m = re.search(r'(\d{4})\s+(\w+)\.pdf', fname)
        if not m:
            return None

        year = int(m.group(1))
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
        }
        month = month_map.get(m.group(2), 1)

        text = self._extract_text(pdf_path)
        if not text or len(text) < 50:
            return None

        stmt = Statement(
            file_name=fname,
            account_id=self.account_id,
            period_start=f"{year}-{month:02d}-01",
            period_end=f"{year}-{month:02d}-28",
        )

        # Parse period from text for more accuracy
        pm = re.search(r'Statement Period:\s*(\d{2}/\d{2}/\d{4})\s*to\s*(\d{2}/\d{2}/\d{4})', text)
        if pm:
            parts = pm.group(1).split('/')
            stmt.period_start = f"{parts[2]}-{parts[0]}-{parts[1]}"
            parts = pm.group(2).split('/')
            stmt.period_end = f"{parts[2]}-{parts[0]}-{parts[1]}"

        # Statement totals
        m = re.search(r'Deposits/Credits\s+\$([\d,]+\.\d{2})', text)
        if m:
            stmt.deposits_total = float(m.group(1).replace(',', ''))

        m = re.search(r'Withdrawals/Debits\s+\$([\d,]+\.\d{2})', text)
        if m:
            stmt.withdrawals_total = float(m.group(1).replace(',', ''))

        m = re.search(r'Beginning Balance\s+\$([\d,]+\.\d{2})', text)
        if m:
            stmt.opening_balance = float(m.group(1).replace(',', ''))

        m = re.search(r'Ending Balance\s+\$([\d,]+\.\d{2})', text)
        if m:
            stmt.closing_balance = float(m.group(1).replace(',', ''))

        # Parse transactions
        self._parse_transactions(text, stmt, year, month)
        self.validate_statement(stmt)

        return stmt

    def _extract_text(self, pdf_path: str) -> str:
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

    def _parse_transactions(self, text: str, stmt: Statement,
                            year: int, month: int):
        """Parse USAA multi-line transaction format."""
        lines = text.split('\n')
        in_transactions = False
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            upper = line.upper()

            if 'TRANSACTIONS' in upper:
                in_transactions = True
                i += 1
                continue

            if not in_transactions:
                i += 1
                continue

            # Skip non-transaction content
            if upper.startswith('DATE DESCRIPTION') or upper == '(CONTINUED)':
                i += 1
                continue
            if upper.startswith('ONLINE:') or upper.startswith('INTEREST PAID INFORMATION'):
                i += 1
                continue
            if 'IMPORTANT INFORMATION' in upper:
                in_transactions = False
                i += 1
                continue

            # Transaction: MM/DD desc $debit|0 $credit|0 $balance
            txn_match = re.match(
                r'^(\d{2}/\d{2})\s+'
                r'(.+?)\s+'
                r'(\$[\d,]+\.\d{2}|0)\s+'
                r'(\$[\d,]+\.\d{2}|0)\s+'
                r'\$([\d,]+\.\d{2})\s*$',
                line,
            )

            if txn_match:
                date_str = txn_match.group(1)
                desc = txn_match.group(2).strip()
                debit_str = txn_match.group(3)
                credit_str = txn_match.group(4)
                balance = float(txn_match.group(5).replace(',', ''))

                debit = float(debit_str.replace('$', '').replace(',', '')) if debit_str != '0' else 0
                credit = float(credit_str.replace('$', '').replace(',', '')) if credit_str != '0' else 0

                # Collect continuation lines
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    if re.match(r'^\d{2}/\d{2}\s', next_line) or not next_line:
                        break
                    if re.match(r'^(Online:|Page\s+\d|USAA\s+(CLASSIC|FEDERAL)|\d{9})', next_line):
                        j += 1
                        continue
                    if 'IMPORTANT' in next_line.upper():
                        break
                    desc += ' ' + next_line
                    j += 1

                # Parse date
                month_num = int(date_str.split('/')[0])
                day = int(date_str.split('/')[1])
                full_date = f"{year}-{month_num:02d}-{day:02d}"
                if month_num < month:
                    full_date = f"{year + 1}-{month_num:02d}-{day:02d}"

                # Skip balance entries
                if 'Beginning Balance' in desc or 'Ending Balance' in desc:
                    i = j
                    continue

                txn = Transaction(
                    date=full_date,
                    description=desc,
                    amount=credit if credit > 0 else debit,
                    type='deposit' if credit > 0 else 'withdrawal',
                    balance=balance,
                )

                if credit > 0:
                    stmt.deposits.append(txn)
                elif debit > 0:
                    stmt.withdrawals.append(txn)
                stmt.all_transactions.append(txn)

                i = j
                continue

            i += 1
