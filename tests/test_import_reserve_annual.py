"""Run: py -3.12 -m unittest discover -s tests -p test_import_reserve_annual.py"""
from decimal import Decimal
import unittest

from scripts.import_data import ROOT, identifier, parse_value, read_reserve_records


class ReserveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = read_reserve_records(ROOT / 'CN230 Petrolium Data' / 'Reserve-2')

    def test_actual_files_and_units(self):
        self.assertEqual(len(self.records), 1200)
        self.assertEqual({r['year'] for r in self.records}, set(range(2017, 2026)))
        self.assertEqual({r['unit'] for r in self.records}, {'MMbbl', 'Bcf'})
        self.assertEqual(sum(r['value'] is None for r in self.records), 629)

    def test_cached_external_formula_is_recorded(self):
        external = [r for r in self.records if '[1]' in r['formula']]
        self.assertEqual(len(external), 1)
        self.assertEqual(external[0]['value'], Decimal('23.106272'))

    def test_zero_is_not_missing_and_rounding_is_explicit(self):
        self.assertEqual(parse_value(0), (Decimal(0), Decimal('0.000000')))
        self.assertEqual(parse_value(None), (None, None))
        self.assertEqual(parse_value('0.0000005')[1], Decimal('0.000001'))

    def test_invalid_numbers_rejected(self):
        for value in (-1, True, 'NaN', 'Infinity', '1000000000000', '=1+1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_value(value)

    def test_stable_ids_are_unique_for_all_source_grains(self):
        ids = {identifier('RA_', r['product'], r['block'].casefold(), r['unit'], r['year']) for r in self.records}
        self.assertEqual(len(ids), 1200)
        self.assertTrue(all(len(code) <= 50 for code in ids))


if __name__ == '__main__':
    unittest.main()
