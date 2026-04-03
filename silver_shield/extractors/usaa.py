"""
USAA bank statement extractor.

USAA text-embedded PDFs use a multi-line transaction format where
amounts appear on separate lines from the description:

    MM/DD  DESCRIPTION LINE 1
           CONTINUATION LINE(S)
    $XX.XX                        <- debit (or "0")
    0 or $XX.XX                   <- credit (or "0")
    $X,XXX.XX                     <- running balance

Uses pdfplumber for text extraction (NOT OCR).
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pdfplumber

from .base import BaseExtractor, Statement, Transaction


class USAAExtractor(BaseExtractor):
    """Extracts transactions from USAA bank statement PDFs."""

    def extract(self, pdf_path: str) -> Optional[Statement]:
        fname = Path(pdf_path).name
        text = self._extract_text(pdf_path)
        if not text or len(text) < 50:
            return None

        period_start, period_end = self._parse_period(text, fname)
        if not period_end:
            return None

        account_id = self._parse_account(text) or self.account_id

        stmt = Statement(
            file_name=fname,
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
        )

        self._parse_summary(text, stmt)
        self._parse_transactions(text, stmt)
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

    def _parse_period(self, text: str, fname: str) -> tuple[str, str]:
        # Text: "Statement Period: 11/11/2025 to 12/11/2025"
        m = re.search(
            r'Statement\s+Period[:\s]+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})',
            text
        )
        if m:
            start = datetime.strptime(m.group(1), "%m/%d/%Y")
            end = datetime.strptime(m.group(2), "%m/%d/%Y")
            return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

        # Filename: "USAA_x7355_2025-11-11_to_2025-12-11_Statement.pdf"
        m = re.search(r'(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})', fname)
        if m:
            return m.group(1), m.group(2)

        return "", ""

    def _parse_account(self, text: str) -> str:
        m = re.search(r'Account\s+Number[:\s]+\d*?(\d{4})\b', text)
        return m.group(1) if m else ""

    def _parse_summary(self, text: str, stmt: Statement):
        m = re.search(r'Beginning\s+Balance\s+\$?([\d,]+\.\d{2})', text)
        if m:
            stmt.opening_balance = float(m.group(1).replace(',', ''))

        m = re.search(r'Ending\s+Balance\s+\$?([\d,]+\.\d{2})', text)
        if m:
            stmt.closing_balance = float(m.group(1).replace(',', ''))

        m = re.search(r'Deposits?/Credits?\s+\$?([\d,]+\.\d{2})', text)
        if m:
            stmt.deposits_total = float(m.group(1).replace(',', ''))

        m = re.search(r'Withdrawals?/Debits?\s+\$?([\d,]+\.\d{2})', text)
        if m:
            stmt.withdrawals_total = float(m.group(1).replace(',', ''))

    def _parse_transactions(self, text: str, stmt: Statement):
        """
        Parse USAA transactions. pdfplumber renders each as a single line:
          MM/DD DESCRIPTION $DEBIT 0 $BALANCE   (withdrawal)
          MM/DD DESCRIPTION 0 $CREDIT $BALANCE  (deposit)
        Continuation description lines follow without a date prefix.
        """
        lines = text.split('\n')
        year_start = int(stmt.period_start[:4]) if stmt.period_start else 2025
        year_end = int(stmt.period_end[:4]) if stmt.period_end else 2025
        month_end = int(stmt.period_end[5:7]) if stmt.period_end else 12

        in_txns = False
        last_txn = None

        # MM/DD desc $debit|0 $credit|0 $balance
        TXN_RE = re.compile(
            r'^(\d{2}/\d{2})\s+'
            r'(.+?)\s+'
            r'(\$[\d,]+\.\d{2}|0)\s+'
            r'(\$[\d,]+\.\d{2}|0)\s+'
            r'\$([\d,]+\.\d{2})$'
        )

        for line in lines:
            s = line.strip()

            if re.match(r'^Transactions\b', s) or (s.startswith('Date') and 'Description' in s):
                in_txns = True
                continue
            if 'IMPORTANT INFORMATION' in s or 'Interest Paid Information' in s:
                in_txns = False
                continue
            if not in_txns or not s:
                continue
            if any(skip in s for skip in [
                'USAA CLASSIC', 'USAA FEDERAL', 'Account Number',
                'Statement Period', 'Online: usaa.com', 'Page ',
                'Transactions (continued)', '022568323', 'Mobile: #8722',
            ]):
                continue

            m = TXN_RE.match(s)
            if m:
                date_str, desc = m.group(1), m.group(2).strip()
                debit_s, credit_s = m.group(3), m.group(4)
                balance = float(m.group(5).replace(',', ''))

                if 'Beginning Balance' in desc or 'Ending Balance' in desc:
                    last_txn = None
                    continue

                debit = float(debit_s.replace('$', '').replace(',', '')) if debit_s != '0' else 0.0
                credit = float(credit_s.replace('$', '').replace(',', '')) if credit_s != '0' else 0.0

                month = int(date_str.split('/')[0])
                day = int(date_str.split('/')[1])
                yr = year_start if month > month_end else year_end

                amount = credit if credit > 0 else debit
                txn_type = 'deposit' if credit > 0 else 'withdrawal'

                txn = Transaction(
                    date=f"{yr}-{month:02d}-{day:02d}",
                    description=desc,
                    amount=amount,
                    type=txn_type,
                    balance=balance,
                )

                if txn_type == 'deposit':
                    stmt.deposits.append(txn)
                else:
                    stmt.withdrawals.append(txn)
                stmt.all_transactions.append(txn)
                last_txn = txn
                continue

            # Continuation description line
            if last_txn and not re.match(r'^\d{2}/\d{2}\s', s):
                last_txn.description += ' | ' + s
