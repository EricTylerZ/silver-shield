"""
OCR-based extractor for image-based bank statement PDFs.

Uses pdfplumber first (fast, accurate for text-embedded PDFs),
then falls back to tesseract OCR for truly scanned documents.
"""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import pdfplumber

from .base import BaseExtractor, Statement, Transaction


class OCRExtractor(BaseExtractor):
    """Generic extractor with OCR fallback for image-based PDFs."""

    def extract(self, pdf_path: str) -> Optional[Statement]:
        """Extract statement-level data (totals, period) from image PDFs."""
        fname = Path(pdf_path).name

        # Try pdfplumber first
        text = self._try_pdfplumber(pdf_path)
        if not text or len(text) < 50:
            text = self._try_tesseract(pdf_path)

        if not text or len(text) < 30:
            return None

        stmt = Statement(
            file_name=fname,
            account_id=self.account_id,
            period_start="",
            period_end="",
        )

        # Try to extract period
        self._parse_period(text, stmt, fname)

        # Try to extract totals (various formats)
        self._parse_totals(text, stmt)

        # Try to extract individual transactions
        self._parse_transactions(text, stmt)

        return stmt

    def _try_pdfplumber(self, pdf_path: str) -> str:
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

    def _try_tesseract(self, pdf_path: str) -> str:
        """Convert PDF pages to images and OCR them."""
        try:
            tmpdir = tempfile.mkdtemp()
            subprocess.run(
                ['pdftoppm', '-png', '-r', '200', pdf_path, f'{tmpdir}/page'],
                capture_output=True, timeout=60,
            )
            pages = sorted(Path(tmpdir).glob('page-*.png'))
            text = ""
            for p in pages:
                r = subprocess.run(
                    ['tesseract', str(p), 'stdout', '--psm', '6'],
                    capture_output=True, text=True, timeout=60,
                )
                if r.returncode == 0:
                    text += r.stdout + "\n\n"
            return text
        except Exception:
            return ""

    def _parse_period(self, text: str, stmt: Statement, fname: str):
        """Try multiple patterns to find statement period."""
        # Pattern: MM/DD/YY to MM/DD/YY
        m = re.search(r'(\d{2}/\d{2}/\d{2,4})\s*(?:to|thru|through|-)\s*(\d{2}/\d{2}/\d{2,4})', text, re.IGNORECASE)
        if m:
            stmt.period_start = self._normalize_date(m.group(1))
            stmt.period_end = self._normalize_date(m.group(2))
            return

        # Pattern from filename: MM-DD-YY-MM-DD-YY
        m = re.search(r'(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', fname)
        if m:
            sm, sd, sy, em, ed, ey = m.groups()
            stmt.period_start = f"20{sy}-{sm}-{sd}"
            stmt.period_end = f"20{ey}-{em}-{ed}"

    def _normalize_date(self, date_str: str) -> str:
        """Convert various date formats to YYYY-MM-DD."""
        parts = date_str.split('/')
        if len(parts) == 3:
            m, d, y = parts
            if len(y) == 2:
                y = '20' + y
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        return date_str

    def _parse_totals(self, text: str, stmt: Statement):
        """Extract balance and total information."""
        patterns = [
            (r'BEGINNING BALANCE.*?\$?\s*([\d,]+\.\d{2})', 'opening_balance'),
            (r'ENDING BALANCE.*?\$?\s*([\d,]+\.\d{2})', 'closing_balance'),
            (r'DEPOSITS.*?\+?\s*([\d,]+\.\d{2})', 'deposits_total'),
            (r'(?:CHECKS|WITHDRAWALS|DEBITS).*?-?\s*([\d,]+\.\d{2})', 'withdrawals_total'),
        ]
        for pattern, attr in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                setattr(stmt, attr, float(m.group(1).replace(',', '')))

    def _parse_transactions(self, text: str, stmt: Statement):
        """Try to extract individual transactions from OCR text."""
        lines = text.split('\n')
        for line in lines:
            stripped = line.strip()
            # Generic: MM/DD description amount
            m = re.match(r'^(\d{1,2}/\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', stripped)
            if m:
                date_str = m.group(1)
                desc = m.group(2).strip()
                amount = float(m.group(3).replace(',', ''))

                year = stmt.period_end[:4] if stmt.period_end else "2025"
                parts = date_str.split('/')
                full_date = f"{year}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"

                txn = Transaction(
                    date=full_date,
                    description=desc,
                    amount=amount,
                )
                stmt.all_transactions.append(txn)
