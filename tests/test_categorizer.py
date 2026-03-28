"""Tests for deposit categorization."""

import unittest
from silver_shield.extractors.base import Transaction
from silver_shield.categorizers.deposits import DepositCategorizer, DEFAULT_RULES


class TestDepositCategorizer(unittest.TestCase):

    def setUp(self):
        self.categorizer = DepositCategorizer()

    def _txn(self, desc, amount=100.0):
        return Transaction(date="2025-01-01", description=desc, amount=amount, type="deposit")

    def test_payroll_detection(self):
        txn = self._txn("ACH DEP 012925 APOLLO HOME CARE DIRECT DEP")
        self.assertEqual(self.categorizer.categorize(txn), "PAYROLL/INCOME")

    def test_gusto_payroll(self):
        txn = self._txn("GUSTO 04/15 PAYROLL")
        self.assertEqual(self.categorizer.categorize(txn), "PAYROLL/INCOME")

    def test_crypto_coinbase(self):
        txn = self._txn("COINBASE INC. 8889087930")
        self.assertEqual(self.categorizer.categorize(txn), "CRYPTO_EXCHANGE")

    def test_crypto_kraken(self):
        txn = self._txn("KRAKEN EXCHANGE DEPOSIT")
        self.assertEqual(self.categorizer.categorize(txn), "CRYPTO_EXCHANGE")

    def test_business_income_stripe(self):
        txn = self._txn("STRIPE TRANSFER")
        self.assertEqual(self.categorizer.categorize(txn), "BUSINESS_INCOME")

    def test_transfer_centier(self):
        txn = self._txn("CENTIER EXT TRNSFR John Doe")
        self.assertEqual(self.categorizer.categorize(txn), "TRANSFER")

    def test_transfer_usaa(self):
        txn = self._txn("USAA EXT-INTRNT TRANSFER J DOE")
        self.assertEqual(self.categorizer.categorize(txn), "TRANSFER")

    def test_zelle(self):
        txn = self._txn("USAA CREDIT Zelle: Jane Smith")
        self.assertEqual(self.categorizer.categorize(txn), "ZELLE")

    def test_interest(self):
        txn = self._txn("INTEREST PAID")
        self.assertEqual(self.categorizer.categorize(txn), "INTEREST")

    def test_iod_interest(self):
        txn = self._txn("IOD INTEREST PAID")
        self.assertEqual(self.categorizer.categorize(txn), "INTEREST")

    def test_return_refund(self):
        txn = self._txn("4877 RTN OFFICE DEPOT 00 DENVER CO")
        self.assertEqual(self.categorizer.categorize(txn), "RETURN/REFUND")

    def test_generic_deposit_bare(self):
        txn = self._txn("DEPOSIT")
        cat = self.categorizer.categorize(txn)
        self.assertEqual(cat, "GENERIC_DEPOSIT")
        self.assertTrue(self.categorizer.is_possible_parent_debt(txn))

    def test_generic_deposit_mobile(self):
        txn = self._txn("DEPOSIT@MOBILE")
        cat = self.categorizer.categorize(txn)
        self.assertEqual(cat, "GENERIC_DEPOSIT")

    def test_peer_payment_venmo(self):
        txn = self._txn("ACH DEP 101725 VENMO CASHOUT")
        self.assertEqual(self.categorizer.categorize(txn), "PEER_PAYMENT")

    def test_schwab_transfer(self):
        txn = self._txn("SCHWAB BROKERAGE MONEYLINK")
        self.assertEqual(self.categorizer.categorize(txn), "BROKERAGE_TRANSFER")

    def test_other_fallback(self):
        txn = self._txn("CASH REWARDS CREDIT")
        self.assertEqual(self.categorizer.categorize(txn), "OTHER")

    def test_parent_debt_identification(self):
        deposits = [
            self._txn("DEPOSIT", 3000),
            self._txn("ACH DEP GUSTO PAYROLL", 2500),
            self._txn("COINBASE INC.", 5000),
            self._txn("DEPOSIT", 4200),
        ]
        parents = self.categorizer.identify_parent_deposits(deposits)
        self.assertEqual(len(parents), 2)
        self.assertEqual(parents[0].amount, 3000)
        self.assertEqual(parents[1].amount, 4200)

    def test_summary_statistics(self):
        deposits = [
            self._txn("DEPOSIT", 3000),
            self._txn("DEPOSIT", 4200),
            self._txn("ACH DEP GUSTO PAYROLL", 2500),
        ]
        summary = self.categorizer.summary(deposits)
        self.assertIn("GENERIC_DEPOSIT", summary)
        self.assertEqual(summary["GENERIC_DEPOSIT"]["count"], 2)
        self.assertEqual(summary["GENERIC_DEPOSIT"]["total"], 7200)
        self.assertTrue(summary["GENERIC_DEPOSIT"]["is_parent_candidate"])


if __name__ == "__main__":
    unittest.main()
