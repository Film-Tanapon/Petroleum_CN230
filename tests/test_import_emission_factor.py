"""Run independently: py -3.12 -m unittest discover -s tests -p test_import_emission_factor.py"""
import unittest
from unittest.mock import MagicMock, patch

from scripts.import_data import COLUMNS, DEFAULT_FILE, read_emission_records, resolve_reference


class ExcelValidationTests(unittest.TestCase):
    def read_rows(self, rows):
        book = MagicMock()
        book.sheetnames = ["MySQL_Import_Ready"]
        book.__getitem__.return_value.iter_rows.return_value = iter([COLUMNS, *rows])
        with patch("scripts.import_data.load_workbook", return_value=book):
            return read_emission_records("unused.xlsx")

    def test_actual_workbook_has_35_valid_factors(self):
        self.assertEqual(len(read_emission_records(DEFAULT_FILE)), 35)

    def test_duplicate_factor_is_rejected(self):
        row = ("EF-1", "PROD-NG", "UNIT-MJ", 1, "Stationary", "NCV")
        with self.assertRaisesRegex(ValueError, "duplicate factor_id"):
            self.read_rows([row, row])

    def test_invalid_values_are_rejected(self):
        for value in (None, -1, 10000, "NaN", "Infinity", "=1+1", 0.0000001, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "factor_value"):
                self.read_rows([("EF-1", "PROD-NG", "UNIT-MJ", value, "Stationary", "NCV")])

    def test_reuses_existing_product_id(self):
        cur = MagicMock()
        cur.fetchall.return_value = [("P02", "Natural Gas")]
        self.assertEqual(resolve_reference(cur, "Product", "PROD-NG", ("Natural Gas",), {}), "P02")
        self.assertEqual(cur.execute.call_count, 1)

    def test_ambiguous_product_is_rejected(self):
        cur = MagicMock()
        cur.fetchall.return_value = [("P02", "Natural Gas"), ("P99", "natural gas")]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            resolve_reference(cur, "Product", "PROD-NG", ("Natural Gas",), {})

    def test_conflicting_id_is_rejected(self):
        cur = MagicMock()
        cur.fetchall.return_value = [("PROD-NG", "Diesel")]
        with self.assertRaisesRegex(ValueError, "already used"):
            resolve_reference(cur, "Product", "PROD-NG", ("Natural Gas",), {})


if __name__ == "__main__":
    unittest.main()
