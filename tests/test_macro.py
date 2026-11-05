"""Regression tests for the dangerous failure modes, without external services."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_common import ET, business_age, document, missing, number, record, source, spread, write_json
from fetch_macro import FED, collect, parse_bp, parse_bund, parse_ecb, parse_euribor, parse_treasury
from validate_macro import validate

NOW = datetime(2026, 11, 5, 18, tzinfo=timezone.utc)
ORIGIN = source("Test publisher", "https://example.org/feed", "test")


def treasury(day="2026-11-04", two="4.2", ten="4.6"):
    return f'<feed xmlns:d="urn:d" xmlns:m="urn:m"><m:properties><d:NEW_DATE>{day}T00:00:00</d:NEW_DATE><d:BC_2YEAR>{two}</d:BC_2YEAR><d:BC_10YEAR>{ten}</d:BC_10YEAR></m:properties></feed>'


def euribor():
    return '<Report xmlns="test"><period value="2026-11-04">' + ''.join(
        f'<rate name="{n} month (act/360)"><intr value="{v}"/></rate>'
        for n, v in [(1, 2), (3, 2.1), (6, 2.2), (12, 2.3)]) + '<rate name="3 month (act/365)"><intr value="9"/></rate></period></Report>'


def bp(values=None):
    return json.dumps({"extension": {"series": [{"id": 12099459}]}, "id": ["country", "reference_date"],
                       "size": [1, 2], "dimension": {"reference_date": {"category": {"index": ["2026-11-02", "2026-11-03"]}}},
                       "value": values if values is not None else [3.8, 3.7]})


def ecb(key, future=False):
    header = 'KEY,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT,UNIT_MULT\n'
    return header + f'FM.{key},2026-09-16,2.5,A,PCPA,0\n' + (f'FM.{key},2026-12-16,3,A,PCPA,0\n' if future else '')


class ParserTests(unittest.TestCase):
    def test_treasury_null_tenor_is_not_zero(self):
        with self.assertRaises(ValueError):
            parse_treasury(treasury(two=""))

    def test_treasury_latest_and_units(self):
        self.assertEqual(parse_treasury(treasury()), ("2026-11-04", 4.2, 4.6))

    def test_non_finite_and_extreme_values_rejected(self):
        for value in ["NaN", "inf", "51", "-11", True, ""]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value)

    def test_euribor_uses_act360_not_act365(self):
        self.assertEqual(parse_euribor(euribor())[1]["3m"], 2.1)

    def test_euribor_missing_tenor_rejected(self):
        with self.assertRaises(ValueError):
            parse_euribor(euribor().replace('12 month', '9 month'))

    def test_external_entities_are_rejected(self):
        with self.assertRaises(Exception):
            ET.fromstring('<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>')

    def test_bpstat_dense_and_sparse_values(self):
        self.assertEqual(parse_bp(bp()), {"2026-11-02": 3.8, "2026-11-03": 3.7})
        self.assertEqual(parse_bp(bp({"1": 3.7})), {"2026-11-03": 3.7})

    def test_bpstat_series_identity(self):
        with self.assertRaises(ValueError):
            parse_bp(bp().replace('12099459', '12099460'))

    def test_bundesbank_missing_observation_excluded(self):
        self.assertEqual(parse_bund('date,value\n2026-11-03,2.9\n2026-11-04,.\n'), {"2026-11-03": 2.9})

    def test_ecb_announced_future_rate_is_not_current(self):
        key = 'B.U2.EUR.4F.KR.DFR.LEV'
        self.assertEqual(parse_ecb(ecb(key, True), key, '2026-11-05'), ('2026-09-16', 2.5))

    def test_ecb_wrong_series_or_units_rejected(self):
        key = 'B.U2.EUR.4F.KR.DFR.LEV'
        for text in [ecb(key).replace('PCPA', 'USD'), ecb(key).replace(',0\n', ',2\n'), ecb(key).replace('DFR', 'WRONG')]:
            with self.assertRaises(ValueError):
                parse_ecb(text, key, '2026-11-05')


class ContractTests(unittest.TestCase):
    def test_weekend_allowance_and_stale_data(self):
        self.assertEqual(business_age(date(2026, 10, 30), date(2026, 11, 2)), 1)
        stale = record(3, '2026-10-28', ORIGIN, NOW)
        self.assertEqual(stale['status'], 'stale')
        self.assertFalse(stale['usable'])
        with self.assertRaises(ValueError):
            record(3, '2026-11-06', ORIGIN, NOW)

    def test_spread_sign_and_basis_point_conversion(self):
        left = record(4.6, '2026-11-04', ORIGIN, NOW)
        right = record(4.2, '2026-11-04', ORIGIN, NOW)
        self.assertEqual(spread(left, right, '10y', '2y', NOW)['value'], 40)
        self.assertEqual(spread(right, left, '10y', '2y', NOW)['value'], -40)

    def test_spread_refuses_mismatched_or_stale_dates(self):
        for day in ['2026-11-03', '2026-10-01']:
            r = spread(record(3.8, day, ORIGIN, NOW), record(3.2, '2026-11-04', ORIGIN, NOW), 'pt', 'de', NOW)
            self.assertIsNone(r['value'])
            self.assertFalse(r['usable'])

    def test_all_provider_failures_still_emit_complete_error_contracts(self):
        with patch('fetch_macro.download', side_effect=TimeoutError('timeout')):
            results = collect(NOW)
        for name, data in results.items():
            validate(name, data, NOW)
            self.assertEqual(data['status'], 'unavailable')
            self.assertTrue(all(r['value'] is None for r in data['records'].values()))

    def test_provider_isolation_policy_dates_and_common_spread_date(self):
        def fake_download(url):
            if 'treasury.gov' in url:
                return treasury()
            if url == FED:
                raise TimeoutError('Fed offline')
            if 'suomenpankki' in url:
                return euribor()
            if 'bportugal' in url:
                return bp()
            if 'bundesbank' in url:
                return 'date,value\n2026-11-03,3.0\n2026-11-05,3.1\n'
            if 'ecb.europa.eu' in url:
                return ecb(url.split('/FM/')[1].split('?')[0])
            raise AssertionError(url)
        with patch('fetch_macro.download', side_effect=fake_download):
            results = collect(NOW)
        for name, data in results.items():
            validate(name, data, NOW)
        rates = results['interest_rates']['records']
        self.assertIsNone(rates['fed_target_upper']['value'])
        self.assertTrue(rates['ecb_deposit']['usable'])
        self.assertEqual(rates['ecb_deposit']['effective_date'], '2026-09-16')
        bonds = results['sovereign_bonds']['records']
        self.assertEqual(bonds['de_10y']['observation_date'], '2026-11-05')
        self.assertEqual(bonds['pt_de_10y_spread']['observation_date'], '2026-11-03')
        self.assertEqual(bonds['pt_de_10y_spread']['value'], 70)

    def test_atomic_json_and_snapshot(self):
        payload = document({'rate': missing(ORIGIN, NOW, 'no response')}, NOW)
        with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='.test-macro-') as temp, patch.dict(os.environ, MARKET_DATA_DIR=temp):
            write_json('test', payload, NOW)
            latest = json.loads((Path(temp) / 'test.json').read_text())
            snapshots = list(Path(temp).glob('history/*/*.json'))
            self.assertEqual(latest, payload)
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(json.loads(snapshots[0].read_text()), payload)


if __name__ == '__main__':
    unittest.main()
